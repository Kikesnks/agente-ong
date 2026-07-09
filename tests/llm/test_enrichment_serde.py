"""Tests de `enriched_report_to_dict`/`enriched_report_from_dict` (R7, T11).

Roundtrip fiel de los 3 campos nuevos del filtro semántico, más retrocompatibilidad con
informes pre-R7 (dict sin esas claves) — mismo patrón que `test_report_serde.py` con
`result_type`/R20.
"""

from __future__ import annotations

import json

from agente_ong.llm.enrichment import EnrichedReport
from agente_ong.llm.enrichment_serde import (
    enriched_report_from_dict,
    enriched_report_to_dict,
)
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport


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


# --- Roundtrip completo (R7.2/R7.4) ---


def test_round_trip_preserves_full_enriched_report() -> None:
    kept = _opportunity("kept")
    discarded = _opportunity("discarded")
    unclassified = _opportunity("unclassified")
    enriched = EnrichedReport(
        base=ResearchReport(mode="calls", opportunities=[kept]),
        discarded=[discarded],
        unclassified=[unclassified],
        semantic_filter_applied=True,
    )

    restored = enriched_report_from_dict(enriched_report_to_dict(enriched))

    assert restored.base == enriched.base
    assert restored.discarded == enriched.discarded
    assert restored.unclassified == enriched.unclassified
    assert restored.semantic_filter_applied is True


def test_dict_is_json_serializable_and_survives_json_round_trip() -> None:
    enriched = EnrichedReport(
        base=ResearchReport(mode="calls", opportunities=[_opportunity("a")]),
        discarded=[_opportunity("b")],
        unclassified=[_opportunity("c")],
        semantic_filter_applied=True,
    )

    data = json.loads(json.dumps(enriched_report_to_dict(enriched)))
    restored = enriched_report_from_dict(data)

    assert restored.discarded == enriched.discarded
    assert restored.unclassified == enriched.unclassified


# --- Retrocompatibilidad con informes pre-R7 ---


def test_from_dict_without_new_keys_defaults_to_unapplied_filter() -> None:
    """Un dict pre-R7 (guardado con report_to_dict, sin las 3 claves nuevas) sigue
    reconstruyendo un EnrichedReport válido: base normal, buckets vacíos, filtro no aplicado."""
    report = ResearchReport(mode="calls", opportunities=[_opportunity("a")])
    from agente_ong.ui.report_serde import report_to_dict

    legacy_data = report_to_dict(report)  # sin discarded/unclassified/semantic_filter_applied

    restored = enriched_report_from_dict(legacy_data)

    assert restored.base == report
    assert restored.discarded == []
    assert restored.unclassified == []
    assert restored.semantic_filter_applied is False


# --- Con provider: 3 buckets serializados correctamente (R7.4) ---


def test_to_dict_with_mixed_opportunities_has_correct_buckets() -> None:
    kept = _opportunity("kept")
    discarded = _opportunity("discarded")
    unclassified = _opportunity("unclassified")
    enriched = EnrichedReport(
        base=ResearchReport(mode="calls", opportunities=[kept]),
        discarded=[discarded],
        unclassified=[unclassified],
        semantic_filter_applied=True,
    )

    data = enriched_report_to_dict(enriched)

    assert len(data["opportunities"]) == 1
    assert data["opportunities"][0]["title"]["value"] == "kept"
    assert len(data["discarded"]) == 1
    assert data["discarded"][0]["title"]["value"] == "discarded"
    assert len(data["unclassified"]) == 1
    assert data["unclassified"][0]["title"]["value"] == "unclassified"
    assert data["semantic_filter_applied"] is True
