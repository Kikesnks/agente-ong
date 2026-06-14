"""Tests de la serialización de informes (`ui/report_serde.py`).

Round-trip `report_to_dict`/`report_from_dict` fiel (estados, fuentes, listas) sobre un
informe completo, aptitud JSON del dict, y Markdown con valor, estado de verificación y URL
de fuente por cada dato. _Requirements: 6.2, 7.1, 7.2_
"""

from __future__ import annotations

import json

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
    report_from_dict,
    report_to_dict,
    report_to_markdown,
    report_to_markdown_summary,
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
    assert "Información no resuelta" in md and "importe" in md
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
