"""Test de integración del flujo del grafo de investigación (end-to-end con fakes).

Ejecuta el grafo completo vía la fachada `Investigador` (plan → recall_ledger → search →
read_deep → verify → ask_user/compile_report) con fuentes fake y persistencia SQLite real
(`tmp_path`), tal como lo verá el cliente. Verifica la estructura del `ResearchReport`, la
trazabilidad (SourceRef en cada dato), la verificación cruzada, `failed_sources` ante una
fuente caída y `unresolved` ante "no encontrado". _Requirements: 1.4, 3.1, 4.4_
"""

from pathlib import Path

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.graph import ResearchGraph
from agente_ong.research.investigador import Investigador
from agente_ong.research.models import ResearchReport, ResearchRequest, VerificationStatus
from agente_ong.research.ods_catalogo import OdsEntry
from fakes import FakeFetchSource, FakeSearchSource, make_document, make_hit


def _investigador(sources, db_path: Path, *, max_depth: int = 1) -> Investigador:
    config = ResearchConfig(max_depth=max_depth, db_path=db_path)
    return Investigador(config, sources=sources)


def _calls_request(**kw) -> ResearchRequest:
    kw.setdefault("mode", "calls")
    kw.setdefault("query_terms", ["cultura"])
    return ResearchRequest(**kw)


def _training_request(**kw) -> ResearchRequest:
    kw.setdefault("mode", "training")
    kw.setdefault("query_terms", ["cultura"])
    return ResearchRequest(**kw)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agente_ong.db"


# --- Flujo completo y estructura del informe ---


def test_full_flow_produces_report_with_traceable_opportunities(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[
            make_hit("https://bo.es/c1", source_name="bdns", title="Conv 1", is_official=True),
            make_hit("https://bo.es/c2", source_name="bdns", title="Conv 2", is_official=True),
        ],
    )
    fetch = FakeFetchSource(
        documents={
            "https://bo.es/c1": make_document("https://bo.es/c1", text="detalle c1"),
            "https://bo.es/c2": make_document("https://bo.es/c2", text="detalle c2"),
        }
    )

    with _investigador([bdns, fetch], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    assert isinstance(report, ResearchReport)
    assert report.mode == "calls"
    assert len(report.opportunities) == 2

    # Requirement 1.4: cada convocatoria incluye una URL de fuente verificable.
    for opp in report.opportunities:
        assert opp.url.value is not None
        assert opp.url.sources, "el dato debe ser trazable a su fuente (SourceRef)"
        ref = opp.url.sources[0]
        assert ref.url == opp.url.value
        assert ref.source_name == "bdns" and ref.is_official is True
        # El título también es trazable.
        assert opp.title.sources and opp.title.sources[0].source_name == "bdns"

    # El ledger del informe recoge las fuentes consultadas.
    assert report.ledger, "el informe debe listar las fuentes consultadas"


# --- Verificación cruzada (Requirement 4.4; regla R14 de investigador-v2) ---


def test_cross_verification_statuses(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # REGLA v2 (R14): la misma URL cuenta UNA sola vez aunque la devuelvan fuentes
    # distintas. c1 (bdns + tavily, misma URL normalizada) ya NO es VERIFIED: una URL =
    # una fuente, y al colapsar sobrevive la oficial -> OFFICIAL_UNCROSSED. VERIFIED exige
    # corroboración entre URLs DISTINTAS, que la agrupación por URL actual no produce
    # (llegará con la agrupación semántica, SPEC 2+). c3 solo no oficial -> UNCROSSED.
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[
            make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True),
            make_hit("https://bo.es/c2", source_name="bdns", title="C2", is_official=True),
        ],
    )
    tavily = FakeSearchSource(
        name="tavily",
        is_official=False,
        hits=[
            make_hit("HTTPS://bo.es/c1/", source_name="tavily", title="C1 dup"),
            make_hit("https://bo.es/c3", source_name="tavily", title="C3"),
        ],
    )

    with _investigador([bdns, tavily, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    by_url = {opp.url.value: opp for opp in report.opportunities}
    assert by_url["https://bo.es/c1"].title.status == VerificationStatus.OFFICIAL_UNCROSSED
    assert by_url["https://bo.es/c2"].title.status == VerificationStatus.OFFICIAL_UNCROSSED
    assert by_url["https://bo.es/c3"].title.status == VerificationStatus.UNCROSSED_UNVERIFIED


def test_repeated_url_is_never_verified_and_sources_are_deduped(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # Regresión del caso real del diagnóstico (12-06-2026): la misma URL devuelta varias
    # veces (varias queries de la misma fuente) se marcaba "Verificado (2+ fuentes)" con
    # la URL repetida en la lista de fuentes (R14.4).
    repetida = make_hit("https://web.example/conv", source_name="tavily", title="Conv")
    tavily = FakeSearchSource(name="tavily", hits=[repetida, repetida, repetida])

    with _investigador([tavily, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(query_terms=["agua limpia", "salud mental"]), selected_ods)

    assert len(report.opportunities) == 1
    opp = report.opportunities[0]
    assert opp.title.status == VerificationStatus.UNCROSSED_UNVERIFIED, "nunca VERIFIED"
    # La lista de fuentes del informe no repite URLs (R14.3).
    urls = [ref.url for ref in opp.title.sources]
    assert len(urls) == len(set(urls)) == 1


# --- Fiabilidad: una fuente caída no aborta la investigación ---


def test_failed_source_is_reported_without_aborting(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    caida = FakeSearchSource(name="ted", fail=ConnectionError("ted down"))
    ok = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )

    with _investigador([caida, ok, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    # La fuente caída se reporta...
    assert any(f.source_name == "ted" for f in report.failed_sources)
    # ...pero la investigación continúa con la fuente sana.
    assert len(report.opportunities) == 1
    assert report.opportunities[0].url.value == "https://bo.es/c1"


# --- Veracidad: "no encontrado" pide ayuda al usuario (Requirement 3.1) ---


def test_no_results_yields_unresolved(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    vacia = FakeSearchSource(name="bdns", is_official=True, hits=[])

    with _investigador([vacia, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    assert report.opportunities == []
    assert any(u.topic == "convocatorias" for u in report.unresolved)
    # El mensaje debe orientar sobre qué ayuda se necesita.
    convocatorias = next(u for u in report.unresolved if u.topic == "convocatorias")
    assert convocatorias.help_needed


def test_missing_critical_fields_become_unresolved(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # El importe y el plazo no vienen en la búsqueda -> NOT_FOUND -> unresolved.
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )

    with _investigador([bdns, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    opp = report.opportunities[0]
    assert opp.amount.status == VerificationStatus.NOT_FOUND
    assert opp.deadline.status == VerificationStatus.NOT_FOUND
    topics = {u.topic for u in report.unresolved}
    assert {"importe", "plazo"} <= topics


# --- Derivación de consultas (_derive_queries) ---


def test_derive_queries_skips_single_word_individual_terms(selected_ods: list[OdsEntry]) -> None:
    # Combinada + solo el término multi-palabra como consulta individual;
    # "agua" (una palabra) ya queda cubierto por la combinada y no se lanza suelto.
    # Tras las queries base, _derive_queries añade una query ODS por cada ODS elegido
    # (R25, N->N); este test solo garantiza el prefijo de queries base.
    request = ResearchRequest(mode="calls", query_terms=["agua", "salud mental"])
    texts = [q.text for q in ResearchGraph._derive_queries(request, selected_ods)]
    assert texts[:2] == ["agua salud mental", "salud mental"]


def test_derive_queries_only_combined_when_all_terms_single_word(selected_ods: list[OdsEntry]) -> None:
    # Tras la query base, _derive_queries añade una query ODS por cada ODS elegido
    # (R25, N->N); este test solo garantiza el prefijo de queries base.
    request = ResearchRequest(mode="calls", query_terms=["agua", "cultura"])
    texts = [q.text for q in ResearchGraph._derive_queries(request, selected_ods)]
    assert texts[:1] == ["agua cultura"]


# --- Detalle BDNS: importe y plazo trazables en el informe (R19, investigador-v2) ---


def test_bdns_amount_and_deadline_reach_the_report(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # Una fuente fake que ya trae amount/deadline en el hit (como hará BdnsSource tras el
    # detalle): el informe debe mostrarlos como OFFICIAL_UNCROSSED y trazables a su URL.
    hit = make_hit(
        "https://bo.es/c1", source_name="bdns", title="Conv 1", is_official=True
    )
    hit.amount = "307.600 €"
    hit.deadline = "hasta 2026-12-20 (abierto)"
    bdns = FakeSearchSource(name="bdns", is_official=True, hits=[hit])

    with _investigador([bdns, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    opp = report.opportunities[0]
    assert opp.amount.value == "307.600 €"
    assert opp.deadline.value == "hasta 2026-12-20 (abierto)"
    assert opp.amount.status == VerificationStatus.OFFICIAL_UNCROSSED
    assert opp.amount.sources and opp.amount.sources[0].url == "https://bo.es/c1"
    assert opp.deadline.sources[0].is_official is True


def test_missing_amount_deadline_stay_not_found(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # Sin datos de detalle (hit sin amount/deadline): se mantiene NOT_FOUND, nunca inventa.
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c2", source_name="bdns", title="C2", is_official=True)],
    )
    with _investigador([bdns, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)
    opp = report.opportunities[0]
    assert opp.amount.value is None and opp.amount.status == VerificationStatus.NOT_FOUND
    assert opp.deadline.value is None


# --- Limpieza y acotado del contenido en el informe (R18, investigador-v2) ---


def test_organism_is_cleaned_and_bounded(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # El snippet del organismo llega con plantilla web y muy largo; en el informe debe
    # salir sin cookies/navegación y dentro del límite (organism_max_chars).
    sucio = (
        "Skip to content\nNuestra web utiliza cookies.\n"
        + "Ministerio de Asuntos Sociales " * 40
    )
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[
            make_hit(
                "https://bo.es/c1", source_name="bdns", title="C1", snippet=sucio,
                is_official=True,
            )
        ],
    )
    config = ResearchConfig(max_depth=1, db_path=db_path, organism_max_chars=80)
    with Investigador(config, sources=[bdns, FakeFetchSource()]) as inv:
        report = inv.run(_calls_request(), selected_ods)

    organism = report.opportunities[0].organism.value
    assert organism is not None
    assert "cookies" not in organism and "Skip to content" not in organism
    assert len(organism) <= 81  # 80 + posible elipsis


# --- Exclusión de fuentes por modo (R15, investigador-v2) ---


def test_source_with_excluded_mode_is_not_consulted_in_that_mode(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # El caso real es TED (excluded_modes={"calls"}); aquí con una fake equivalente.
    licitaciones = FakeSearchSource(
        name="ted",
        is_official=True,
        hits=[make_hit("https://ted.eu/lic1", source_name="ted", title="Licitación")],
    )
    licitaciones.excluded_modes = frozenset({"calls"})
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )

    with _investigador([licitaciones, bdns, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    assert licitaciones.search_calls == [], "la fuente excluida del modo no se consulta"
    assert bdns.search_calls, "las demás fuentes siguen consultándose"
    assert [o.url.value for o in report.opportunities] == ["https://bo.es/c1"]


def test_source_without_excluded_modes_behaves_as_before(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    fuente = FakeSearchSource(name="bdns", is_official=True, hits=[])
    with _investigador([fuente, FakeFetchSource()], db_path) as inv:
        inv.run(_calls_request(), selected_ods)
    assert fuente.search_calls, "default excluded_modes vacío => sin cambios"


# --- Selección de fuentes y URLs directas (Requirements 9.1-9.4) ---


def test_enabled_sources_restricts_search_to_subset(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )
    tavily = FakeSearchSource(
        name="tavily",
        hits=[make_hit("https://web.example/x", source_name="tavily", title="X")],
    )
    fetch = FakeFetchSource()

    with _investigador([bdns, tavily, fetch], db_path) as inv:
        report = inv.run(_calls_request(enabled_sources={"bdns", "fake-fetch"}), selected_ods)

    # Solo la fuente activa fue consultada; la desactivada ni se llamó ni aportó hits.
    assert bdns.search_calls, "la fuente activa debe consultarse"
    assert tavily.search_calls == [], "la fuente desactivada no debe consultarse"
    assert [o.url.value for o in report.opportunities] == ["https://bo.es/c1"]


def test_enabled_sources_none_uses_all_sources(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    bdns = FakeSearchSource(name="bdns", is_official=True, hits=[])
    tavily = FakeSearchSource(name="tavily", hits=[])

    with _investigador([bdns, tavily, FakeFetchSource()], db_path) as inv:
        inv.run(_calls_request(), selected_ods)  # enabled_sources=None (default)

    assert bdns.search_calls and tavily.search_calls


def test_direct_url_is_read_even_without_search_hits(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    vacia = FakeSearchSource(name="bdns", is_official=True, hits=[])
    fetch = FakeFetchSource(
        documents={
            "https://ong.example/conv": make_document(
                "https://ong.example/conv", text="detalle de la convocatoria"
            )
        }
    )

    with _investigador([vacia, fetch], db_path) as inv:
        report = inv.run(_calls_request(direct_urls=["https://ong.example/conv"]), selected_ods)

    assert fetch.fetch_calls == ["https://ong.example/conv"]
    # La lectura queda registrada en el ledger del informe (trazabilidad).
    assert any(e.key == "https://ong.example/conv" for e in report.ledger)


def test_direct_url_is_read_with_all_search_sources_disabled(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    bdns = FakeSearchSource(name="bdns", is_official=True, hits=[])
    tavily = FakeSearchSource(name="tavily", hits=[])
    fetch = FakeFetchSource()

    with _investigador([bdns, tavily, fetch], db_path) as inv:
        inv.run(
            _calls_request(
                enabled_sources={"fake-fetch"},  # ambas fuentes de búsqueda desactivadas
                direct_urls=["https://ong.example/directa"],
            ),
            selected_ods,
        )

    assert bdns.search_calls == [] and tavily.search_calls == []
    assert fetch.fetch_calls == ["https://ong.example/directa"]


# --- Lectura profunda v2: gating por result_type, fallback y límites (R23) ---


def test_read_deep_only_fetches_convocatoria_probable_hits(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # bdns -> convocatoria_probable (R20); tavily sin señales -> documento_informativo.
    # Solo el primero consume lectura profunda (23.3); el segundo igualmente aparece en
    # el informe (agrupación por URL no depende del gating de lectura).
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )
    tavily = FakeSearchSource(
        name="tavily",
        hits=[make_hit("https://web.example/info", source_name="tavily", title="Articulo")],
    )
    fetch = FakeFetchSource(
        documents={"https://bo.es/c1": make_document("https://bo.es/c1", text="detalle c1")}
    )

    with _investigador([bdns, tavily, fetch], db_path) as inv:
        report = inv.run(_calls_request(), selected_ods)

    assert fetch.fetch_calls == ["https://bo.es/c1"]
    by_url = {opp.url.value: opp for opp in report.opportunities}
    assert by_url["https://bo.es/c1"].result_type == "convocatoria_probable"
    assert by_url["https://web.example/info"].result_type == "documento_informativo"


def test_read_deep_in_training_mode_fetches_all_hits(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # En modo "training" el gating de R23.3 se desactiva a propósito: TODOS los hits
    # siembran la frontera (no solo "convocatoria_probable"), porque el material
    # informativo es justo lo que se quiere capturar como ejemplo de entrenamiento.
    # A diferencia del modo "calls", training no construye report.opportunities
    # (verify() recolecta resources vía TrainingCollector), así que el test comprueba
    # el gating por lo único que lo refleja aquí: qué URLs se leyeron en profundidad.
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )
    tavily = FakeSearchSource(
        name="tavily",
        hits=[make_hit("https://web.example/info", source_name="tavily", title="Articulo")],
    )
    fetch = FakeFetchSource(
        documents={
            "https://bo.es/c1": make_document("https://bo.es/c1", text="detalle c1"),
            "https://web.example/info": make_document("https://web.example/info", text="info"),
        }
    )

    with _investigador([bdns, tavily, fetch], db_path) as inv:
        inv.run(_training_request(), selected_ods)

    # El gating NO aplica en training: ambos hits se leen en profundidad,
    # incluido el "documento_informativo" (que en modo "calls" quedaría fuera).
    assert set(fetch.fetch_calls) == {"https://bo.es/c1", "https://web.example/info"}


def test_primary_failure_without_fallback_keeps_hit_and_reports_failure(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # firecrawl_max_calls=0 (default, 23.4): el fallback nunca se invoca; el fallo del
    # primario se refleja en failed_sources y el hit conserva sus datos (23.5).
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )
    reader = FakeFetchSource(name="reader", fail=ConnectionError("boom"))
    firecrawl = FakeFetchSource(name="firecrawl")

    config = ResearchConfig(max_depth=1, db_path=db_path)
    with Investigador(config, sources=[bdns, reader, firecrawl]) as inv:
        report = inv.run(_calls_request(), selected_ods)

    assert reader.fetch_calls == ["https://bo.es/c1"]
    assert firecrawl.fetch_calls == []
    assert any(f.source_name == "reader" for f in report.failed_sources)
    assert report.opportunities[0].url.value == "https://bo.es/c1"


def test_fallback_invoked_up_to_firecrawl_max_calls(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # firecrawl_max_calls=1 (23.2/23.4): el fallback se invoca como máximo N veces, una
    # por investigación, no por URL.
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[
            make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True),
            make_hit("https://bo.es/c2", source_name="bdns", title="C2", is_official=True),
        ],
    )
    reader = FakeFetchSource(name="reader", fail=ConnectionError("boom"))
    firecrawl = FakeFetchSource(
        name="firecrawl",
        documents={"https://bo.es/c1": make_document("https://bo.es/c1", text="fallback c1")},
    )

    config = ResearchConfig(max_depth=1, db_path=db_path, firecrawl_max_calls=1)
    with Investigador(config, sources=[bdns, reader, firecrawl]) as inv:
        report = inv.run(_calls_request(), selected_ods)

    assert reader.fetch_calls == ["https://bo.es/c1", "https://bo.es/c2"]
    assert firecrawl.fetch_calls == ["https://bo.es/c1"]  # cupo agotado tras la primera
    assert sum(1 for f in report.failed_sources if f.source_name == "reader") == 2


def test_reader_max_pages_limits_pages_fetched(db_path: Path, selected_ods: list[OdsEntry]) -> None:
    # reader_max_pages (23.4) gana frente a max_pages (50 por defecto con max_depth=1).
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[
            make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True),
            make_hit("https://bo.es/c2", source_name="bdns", title="C2", is_official=True),
        ],
    )
    fetch = FakeFetchSource(
        documents={
            "https://bo.es/c1": make_document("https://bo.es/c1", text="detalle c1"),
            "https://bo.es/c2": make_document("https://bo.es/c2", text="detalle c2"),
        }
    )

    config = ResearchConfig(max_depth=1, db_path=db_path, reader_max_pages=1)
    with Investigador(config, sources=[bdns, fetch]) as inv:
        inv.run(_calls_request(), selected_ods)

    assert fetch.fetch_calls == ["https://bo.es/c1"]
