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
from fakes import FakeFetchSource, FakeSearchSource, make_document, make_hit


def _investigador(sources, db_path: Path, *, max_depth: int = 1) -> Investigador:
    config = ResearchConfig(max_depth=max_depth, db_path=db_path)
    return Investigador(config, sources=sources)


def _calls_request(**kw) -> ResearchRequest:
    kw.setdefault("mode", "calls")
    kw.setdefault("query_terms", ["cultura"])
    return ResearchRequest(**kw)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agente_ong.db"


# --- Flujo completo y estructura del informe ---


def test_full_flow_produces_report_with_traceable_opportunities(db_path: Path) -> None:
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
        report = inv.run(_calls_request())

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


# --- Verificación cruzada (Requirement 4.4) ---


def test_cross_verification_statuses(db_path: Path) -> None:
    # c1 lo devuelven DOS fuentes (oficial + no oficial, misma URL normalizada) -> VERIFIED.
    # c2 solo la oficial -> OFFICIAL_UNCROSSED. c3 solo la no oficial -> UNCROSSED_UNVERIFIED.
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
        report = inv.run(_calls_request())

    by_url = {opp.url.value: opp for opp in report.opportunities}
    assert by_url["https://bo.es/c1"].title.status == VerificationStatus.VERIFIED
    assert by_url["https://bo.es/c2"].title.status == VerificationStatus.OFFICIAL_UNCROSSED
    assert by_url["https://bo.es/c3"].title.status == VerificationStatus.UNCROSSED_UNVERIFIED


# --- Fiabilidad: una fuente caída no aborta la investigación ---


def test_failed_source_is_reported_without_aborting(db_path: Path) -> None:
    caida = FakeSearchSource(name="ted", fail=ConnectionError("ted down"))
    ok = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )

    with _investigador([caida, ok, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request())

    # La fuente caída se reporta...
    assert any(f.source_name == "ted" for f in report.failed_sources)
    # ...pero la investigación continúa con la fuente sana.
    assert len(report.opportunities) == 1
    assert report.opportunities[0].url.value == "https://bo.es/c1"


# --- Veracidad: "no encontrado" pide ayuda al usuario (Requirement 3.1) ---


def test_no_results_yields_unresolved(db_path: Path) -> None:
    vacia = FakeSearchSource(name="bdns", is_official=True, hits=[])

    with _investigador([vacia, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request())

    assert report.opportunities == []
    assert any(u.topic == "convocatorias" for u in report.unresolved)
    # El mensaje debe orientar sobre qué ayuda se necesita.
    convocatorias = next(u for u in report.unresolved if u.topic == "convocatorias")
    assert convocatorias.help_needed


def test_missing_critical_fields_become_unresolved(db_path: Path) -> None:
    # El importe y el plazo no vienen en la búsqueda -> NOT_FOUND -> unresolved.
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit("https://bo.es/c1", source_name="bdns", title="C1", is_official=True)],
    )

    with _investigador([bdns, FakeFetchSource()], db_path) as inv:
        report = inv.run(_calls_request())

    opp = report.opportunities[0]
    assert opp.amount.status == VerificationStatus.NOT_FOUND
    assert opp.deadline.status == VerificationStatus.NOT_FOUND
    topics = {u.topic for u in report.unresolved}
    assert {"importe", "plazo"} <= topics


# --- Derivación de consultas (_derive_queries) ---


def test_derive_queries_skips_single_word_individual_terms() -> None:
    # Combinada + solo el término multi-palabra como consulta individual;
    # "agua" (una palabra) ya queda cubierto por la combinada y no se lanza suelto.
    request = ResearchRequest(mode="calls", query_terms=["agua", "salud mental"])
    texts = [q.text for q in ResearchGraph._derive_queries(request)]
    assert texts == ["agua salud mental", "salud mental"]


def test_derive_queries_only_combined_when_all_terms_single_word() -> None:
    request = ResearchRequest(mode="calls", query_terms=["agua", "cultura"])
    texts = [q.text for q in ResearchGraph._derive_queries(request)]
    assert texts == ["agua cultura"]


# --- Selección de fuentes y URLs directas (Requirements 9.1-9.4) ---


def test_enabled_sources_restricts_search_to_subset(db_path: Path) -> None:
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
        report = inv.run(_calls_request(enabled_sources={"bdns", "fake-fetch"}))

    # Solo la fuente activa fue consultada; la desactivada ni se llamó ni aportó hits.
    assert bdns.search_calls, "la fuente activa debe consultarse"
    assert tavily.search_calls == [], "la fuente desactivada no debe consultarse"
    assert [o.url.value for o in report.opportunities] == ["https://bo.es/c1"]


def test_enabled_sources_none_uses_all_sources(db_path: Path) -> None:
    bdns = FakeSearchSource(name="bdns", is_official=True, hits=[])
    tavily = FakeSearchSource(name="tavily", hits=[])

    with _investigador([bdns, tavily, FakeFetchSource()], db_path) as inv:
        inv.run(_calls_request())  # enabled_sources=None (default)

    assert bdns.search_calls and tavily.search_calls


def test_direct_url_is_read_even_without_search_hits(db_path: Path) -> None:
    vacia = FakeSearchSource(name="bdns", is_official=True, hits=[])
    fetch = FakeFetchSource(
        documents={
            "https://ong.example/conv": make_document(
                "https://ong.example/conv", text="detalle de la convocatoria"
            )
        }
    )

    with _investigador([vacia, fetch], db_path) as inv:
        report = inv.run(_calls_request(direct_urls=["https://ong.example/conv"]))

    assert fetch.fetch_calls == ["https://ong.example/conv"]
    # La lectura queda registrada en el ledger del informe (trazabilidad).
    assert any(e.key == "https://ong.example/conv" for e in report.ledger)


def test_direct_url_is_read_with_all_search_sources_disabled(db_path: Path) -> None:
    bdns = FakeSearchSource(name="bdns", is_official=True, hits=[])
    tavily = FakeSearchSource(name="tavily", hits=[])
    fetch = FakeFetchSource()

    with _investigador([bdns, tavily, fetch], db_path) as inv:
        inv.run(
            _calls_request(
                enabled_sources={"fake-fetch"},  # ambas fuentes de búsqueda desactivadas
                direct_urls=["https://ong.example/directa"],
            )
        )

    assert bdns.search_calls == [] and tavily.search_calls == []
    assert fetch.fetch_calls == ["https://ong.example/directa"]
