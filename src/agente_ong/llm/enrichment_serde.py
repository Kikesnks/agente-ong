"""Serialización de `EnrichedReport` (`EnrichedReport` ⇄ dict) (R7, T11).

Envuelve `report_serde.report_to_dict`/`report_from_dict` (ui/, T10 no se toca) y añade la
clave `semantic_filter_applied`. Vive en `llm/` — no en `ui/report_serde.py` — para que
`report_serde.py` siga sin conocer `llm/` (Opción B, decisión #8, intacta): es esta capa,
no la del investigador ni la de serialización base, la que sabe que el filtro existe.
"""

from __future__ import annotations

from agente_ong.llm.enrichment import EnrichedReport
from agente_ong.research.models import ResearchReport
from agente_ong.ui.report_serde import report_from_dict, report_to_dict


def enriched_report_to_dict(enriched: EnrichedReport) -> dict:
    """Serializa un `EnrichedReport` a un dict apto para JSON (tipos primitivos)."""
    data = report_to_dict(enriched.base)
    data["semantic_filter_applied"] = enriched.semantic_filter_applied
    return data


def enriched_report_from_dict(data: dict) -> EnrichedReport:
    """Reconstruye un `EnrichedReport` desde el dict producido por `enriched_report_to_dict`.

    Retrocompatible con informes pre-R7 (persistidos antes de este cableado): sin la clave
    `semantic_filter_applied`, `.get(..., False)` lo trata como si el filtro nunca se
    hubiera aplicado — mismo patrón que `result_type`/R20 en `report_serde.py`.
    """
    base: ResearchReport = report_from_dict(data)
    return EnrichedReport(
        base=base,
        semantic_filter_applied=data.get("semantic_filter_applied", False),
    )
