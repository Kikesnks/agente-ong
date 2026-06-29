"""Tests de la serialización de informes (`ui/report_serde.py`).

Round-trip `report_to_dict`/`report_from_dict` fiel (estados, fuentes, listas) sobre un
informe completo, aptitud JSON del dict, y Markdown con valor, estado de verificación y URL
de fuente por cada dato. _Requirements: 6.2, 7.1, 7.2_
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agente_ong.research.models import (
    Claim,
    FailedSource,
    GrantOpportunity,
    LedgerEntry,
    ResearchReport,
    SourceRef,
    StoredResource,
    Unresolved,
    VerificationStatus,
)
from agente_ong.ui.report_serde import (
    format_verification_date,
    opportunity_numbers,
    report_from_dict,
    report_to_dict,
    report_to_markdown,
    report_to_markdown_summary,
    url_verification_suffix,
)


def _ref(url: str = "https://bo.es/c1", *, official: bool = True) -> SourceRef:
    return SourceRef(url=url, source_name="bdns" if official else "tavily", is_official=official)


def _sample_report() -> ResearchReport:
    """Informe de ejemplo que ejercita todos los contenedores y estados."""
    official = _ref()
    unofficial = _ref("https://web.example/c1", official=False)
    opp = GrantOpportunity(
        title=Claim(
            field="titulo",
            value="Ayudas cultura",
            status=VerificationStatus.VERIFIED,
            sources=[official, unofficial],
        ),
        organism=Claim(
            field="organismo",
            value="Ministerio",
            status=VerificationStatus.OFFICIAL_UNCROSSED,
            sources=[official],
        ),
        amount=Claim(field="importe", is_critical=True, stale=True),
        deadline=Claim(field="plazo", is_critical=True),
        scope=Claim(field="ambito"),
        url=Claim(
            field="url",
            value="https://bo.es/c1",
            status=VerificationStatus.VERIFIED,
            sources=[official, unofficial],
        ),
        overall_status=VerificationStatus.VERIFIED,
        result_type="convocatoria_probable",
    )
    return ResearchReport(
        mode="calls",
        opportunities=[opp],
        resources=[
            StoredResource(
                path="RECURSOS/ENTRENAMIENTO/doc.pdf",
                source_url="https://x.es/doc.pdf",
                mode_of_capture="download",
                tags=["cultura"],
            )
        ],
        ledger=[
            LedgerEntry(
                key="https://bo.es/c1",
                kind="url",
                outcome="useful",
                content_summary="resumen",
                topics=["cultura"],
                source_ref=official,
            ),
            LedgerEntry(key="cultura", kind="query", outcome="empty"),
        ],
        reused_from_ledger=[LedgerEntry(key="pista", kind="url", outcome="useful")],
        unresolved=[Unresolved(topic="importe", reason="Sin importe.", help_needed="Confirma.")],
        failed_sources=[FailedSource(source_name="ted", error="timeout")],
    )


# --- Round-trip dict (R6.2) ---


def test_round_trip_preserves_full_report() -> None:
    report = _sample_report()
    restored = report_from_dict(report_to_dict(report))
    # Igualdad estructural completa: estados, fuentes, listas y flags incluidos.
    assert restored == report


def test_dict_is_json_serializable_and_survives_json_round_trip() -> None:
    report = _sample_report()
    payload = json.dumps(report_to_dict(report))  # como se guardará en report_json
    assert report_from_dict(json.loads(payload)) == report


def test_round_trip_preserves_status_enums_and_source_flags() -> None:
    restored = report_from_dict(report_to_dict(_sample_report()))
    opp = restored.opportunities[0]
    assert opp.title.status is VerificationStatus.VERIFIED
    assert opp.organism.status is VerificationStatus.OFFICIAL_UNCROSSED
    assert opp.amount.status is VerificationStatus.NOT_FOUND
    assert opp.amount.stale is True and opp.amount.is_critical is True
    officials = [ref.is_official for ref in opp.title.sources]
    assert officials == [True, False]


def test_round_trip_of_empty_report() -> None:
    report = ResearchReport(mode="training")
    assert report_from_dict(report_to_dict(report)) == report


# --- R20: result_type en el serde (round-trip + retrocompatibilidad) ---


def test_result_type_survives_round_trip() -> None:
    restored = report_from_dict(report_to_dict(_sample_report()))
    assert restored.opportunities[0].result_type == "convocatoria_probable"


def test_pre_v2_dict_without_result_type_loads_as_desconocido() -> None:
    # Un informe persistido ANTES de v2 no tiene la clave; debe cargar sin romper.
    data = report_to_dict(_sample_report())
    for opp in data["opportunities"]:
        del opp["result_type"]
    restored = report_from_dict(data)
    assert restored.opportunities[0].result_type == "desconocido"


# --- Markdown (R7.1, R7.2) ---


def test_markdown_includes_value_status_and_source_url_per_claim() -> None:
    md = report_to_markdown(_sample_report())
    assert "Ayudas cultura" in md
    assert "Verificado (2+ fuentes)" in md
    assert "https://bo.es/c1" in md  # URL de la fuente junto al dato
    # Un dato no hallado se presenta como tal, sin inventar valor.
    assert "No encontrado" in md


def test_markdown_includes_unresolved_and_failed_sources_sections() -> None:
    md = report_to_markdown(_sample_report())
    assert "Datos por confirmar" in md and "importe" in md
    assert "Fuentes con problemas" in md and "ted" in md


def test_markdown_without_opportunities_says_so() -> None:
    md = report_to_markdown(ResearchReport(mode="calls"))
    assert "No se encontraron convocatorias" in md


# --- R22: vista resumida ---


def test_summary_has_the_six_fields_and_is_short() -> None:
    md = report_to_markdown_summary(_sample_report())
    for label in ("Organismo", "Importe", "Plazo", "URL", "Verificación"):
        assert label in md
    assert "Ayudas cultura" in md  # título como encabezado
    # Resumida = pocas líneas por convocatoria; mucho más corta que la detallada.
    assert len(md.splitlines()) < len(report_to_markdown(_sample_report()).splitlines())


def test_summary_and_detail_come_from_the_same_report() -> None:
    # Ambas vistas se generan del mismo objeto, sin segunda investigación (R22.4).
    report = _sample_report()
    assert report_to_markdown_summary(report)  # no lanza
    assert report_to_markdown(report)
    # El título de la convocatoria aparece en las dos.
    assert "Ayudas cultura" in report_to_markdown_summary(report)
    assert "Ayudas cultura" in report_to_markdown(report)


def test_summary_lists_informational_apart() -> None:
    from agente_ong.research.models import Claim, GrantOpportunity

    info = GrantOpportunity(
        title=Claim(field="titulo", value="Estudio sobre pobreza"),
        organism=Claim(field="organismo"),
        amount=Claim(field="importe"),
        deadline=Claim(field="plazo"),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value="https://web.example/estudio"),
        overall_status=VerificationStatus.UNCROSSED_UNVERIFIED,
        result_type="documento_informativo",
    )
    report = ResearchReport(mode="calls", opportunities=[info])
    md = report_to_markdown_summary(report)
    assert "Material informativo" in md
    assert "Estudio sobre pobreza" in md
    # Sin convocatorias accionables, lo dice claramente.
    assert "No se encontraron convocatorias" in md


def test_summary_without_content_says_so() -> None:
    md = report_to_markdown_summary(ResearchReport(mode="calls"))
    assert "No se encontraron convocatorias" in md


def _simple_opp(title: str, result_type: str = "convocatoria_probable") -> GrantOpportunity:
    return GrantOpportunity(
        title=Claim(field="titulo", value=title, status=VerificationStatus.VERIFIED),
        organism=Claim(field="organismo"),
        amount=Claim(field="importe"),
        deadline=Claim(field="plazo"),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value=f"https://x.es/{title}"),
        overall_status=VerificationStatus.VERIFIED,
        result_type=result_type,
    )


# --- R14: opportunity_numbers ---


def test_opportunity_numbers_assigns_1_to_n_to_actionable_only() -> None:
    opp_a = _simple_opp("probable", "convocatoria_probable")
    opp_b = _simple_opp("desconocido", "desconocido")
    opp_c = _simple_opp("informativo", "documento_informativo")
    report = ResearchReport(mode="calls", opportunities=[opp_a, opp_b, opp_c])
    numbers = opportunity_numbers(report)
    assert numbers[id(opp_a)] == 1
    assert numbers[id(opp_b)] == 2
    assert id(opp_c) not in numbers
    assert len(numbers) == 2


def test_detail_and_summary_use_same_numbers_for_mixed_report() -> None:
    """R14.2: la vista detallada y la resumida usan los mismos números de convocatoria."""
    opp_probable = _simple_opp("accionable", "convocatoria_probable")
    opp_info = _simple_opp("informativo", "documento_informativo")
    report = ResearchReport(mode="calls", opportunities=[opp_probable, opp_info])
    md_summary = report_to_markdown_summary(report)
    md_detail = report_to_markdown(report)
    assert "### 1. accionable" in md_summary
    assert "### 1. accionable" in md_detail
    assert "Material informativo" in md_detail
    assert "informativo" in md_detail


def test_detail_markdown_separates_informational_section() -> None:
    """report_to_markdown (detallado) tiene sección propia para documentos informativos."""
    info = _simple_opp("estudio", "documento_informativo")
    report = ResearchReport(mode="calls", opportunities=[info])
    md = report_to_markdown(report)
    assert "Material informativo" in md
    assert "estudio" in md
    assert "No se encontraron convocatorias" in md


# --- R15: format_verification_date / url_verification_suffix ---


def test_format_verification_date_returns_dd_mm_yyyy() -> None:
    dt = datetime(2026, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
    assert format_verification_date(dt) == "15-06-2026"


def test_url_suffix_without_sources_is_empty() -> None:
    """R15.3: si claim.sources está vacío no se añade texto de fecha."""
    claim = Claim(field="url", value="https://x.es/c1")
    assert url_verification_suffix(claim) == ""


def test_url_suffix_with_source_includes_date() -> None:
    dt = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    ref = SourceRef(url="https://x.es/c1", source_name="bdns", is_official=True, retrieved_at=dt)
    claim = Claim(field="url", value="https://x.es/c1", sources=[ref])
    assert url_verification_suffix(claim) == " (verificada el 15-06-2026)"


def test_summary_and_detail_url_include_verification_date() -> None:
    """R15.1: la URL con fuentes muestra '(verificada el DD-MM-AAAA)' en ambas vistas."""
    dt = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    ref = SourceRef(url="https://bo.es/c1", source_name="bdns", is_official=True, retrieved_at=dt)
    opp = GrantOpportunity(
        title=Claim(field="titulo", value="Ayudas prueba"),
        organism=Claim(field="organismo"),
        amount=Claim(field="importe"),
        deadline=Claim(field="plazo"),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value="https://bo.es/c1", sources=[ref]),
        overall_status=VerificationStatus.OFFICIAL_UNCROSSED,
        result_type="convocatoria_probable",
    )
    report = ResearchReport(mode="calls", opportunities=[opp])
    md_summary = report_to_markdown_summary(report)
    md_detail = report_to_markdown(report)
    assert "verificada el 15-06-2026" in md_summary
    assert "verificada el 15-06-2026" in md_detail
