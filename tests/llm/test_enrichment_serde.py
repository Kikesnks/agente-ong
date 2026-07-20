"""Tests de `enriched_report_to_dict`/`enriched_report_from_dict` (R7 de
`integracion-llm`, T11; T3 de `descartados-filtro`; R7 de `alineacion-estrategica`,
tarea 7).

Roundtrip fiel de `base` (incluido `filter_verdicts`, T2), `semantic_filter_applied` y
`strategic_alignment` (tarea 7), más retrocompatibilidad con informes pre-R7/pre-tarea-7
(dict sin esas claves) — mismo patrón que `test_report_serde.py` con `result_type`/R20.
"""

from __future__ import annotations

import json

from agente_ong.llm.enrichment import EnrichedReport
from agente_ong.llm.enrichment_serde import (
    enriched_report_from_dict,
    enriched_report_to_dict,
)
from agente_ong.research.alignment import AlineacionEstrategica
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport
from agente_ong.ui.report_serde import report_to_dict


def _opportunity(title_value: str) -> GrantOpportunity:
    def claim(field_name: str, value: str | None = None) -> Claim:
        return Claim(field=field_name, value=value)

    return GrantOpportunity(
        title=claim("titulo", title_value),
        organism=claim("organismo"),
        amount=claim("importe"),
        deadline=claim("plazo"),
        scope=claim("ambito"),
        url=claim("url", f"https://example.org/{title_value}"),
    )


# --- Roundtrip completo, incluido filter_verdicts dentro de base (T2/T3) ---


def test_round_trip_preserves_full_enriched_report() -> None:
    enriched = EnrichedReport(
        base=ResearchReport(
            mode="calls",
            opportunities=[_opportunity("kept"), _opportunity("discarded")],
            filter_verdicts={
                "https://example.org/kept": "si",
                "https://example.org/discarded": "no",
            },
        ),
        semantic_filter_applied=True,
        strategic_alignment={
            "https://example.org/kept": AlineacionEstrategica(
                ods=[3, 5],
                prioridades_geograficas=["América Latina y el Caribe"],
                enfoques_transversales=["Enfoque de derechos humanos"],
                sectores_plan_director=["Gobernabilidad democrática"],
            )
        },
    )

    restored = enriched_report_from_dict(enriched_report_to_dict(enriched))

    assert restored.base == enriched.base
    assert restored.base.filter_verdicts == enriched.base.filter_verdicts
    assert restored.semantic_filter_applied is True
    assert restored.strategic_alignment == enriched.strategic_alignment


def test_dict_is_json_serializable_and_survives_json_round_trip() -> None:
    enriched = EnrichedReport(
        base=ResearchReport(
            mode="calls",
            opportunities=[_opportunity("a")],
            filter_verdicts={"https://example.org/a": "si"},
        ),
        semantic_filter_applied=True,
        strategic_alignment={"https://example.org/a": AlineacionEstrategica(ods=[7])},
    )

    data = json.loads(json.dumps(enriched_report_to_dict(enriched)))
    restored = enriched_report_from_dict(data)

    assert restored.base.filter_verdicts == enriched.base.filter_verdicts
    assert restored.semantic_filter_applied is True
    assert restored.strategic_alignment == enriched.strategic_alignment


# --- Retrocompatibilidad con informes pre-R7 ---


def test_from_dict_without_new_key_defaults_to_unapplied_filter() -> None:
    """Un dict pre-R7 (guardado con report_to_dict, sin semantic_filter_applied ni
    strategic_alignment) sigue reconstruyendo un EnrichedReport válido: base normal,
    filtro no aplicado, alineación vacía."""
    report = ResearchReport(mode="calls", opportunities=[_opportunity("a")])
    legacy_data = report_to_dict(report)  # sin semantic_filter_applied ni strategic_alignment

    restored = enriched_report_from_dict(legacy_data)

    assert restored.base == report
    assert restored.semantic_filter_applied is False
    assert restored.strategic_alignment == {}


def test_from_dict_without_strategic_alignment_key_defaults_to_empty() -> None:
    """Un dict de la era R7/`integracion-llm` (con semantic_filter_applied pero sin
    strategic_alignment, anterior a la tarea 7 de `alineacion-estrategica`) reconstruye
    con alineación vacía, no un KeyError."""
    report = ResearchReport(
        mode="calls",
        opportunities=[_opportunity("a")],
        filter_verdicts={"https://example.org/a": "si"},
    )
    data = report_to_dict(report)
    data["semantic_filter_applied"] = True  # sin "strategic_alignment"

    restored = enriched_report_from_dict(data)

    assert restored.semantic_filter_applied is True
    assert restored.strategic_alignment == {}
