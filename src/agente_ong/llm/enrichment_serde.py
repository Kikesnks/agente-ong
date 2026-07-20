"""Serialización de `EnrichedReport` (`EnrichedReport` ⇄ dict) (R7 de `integracion-llm`,
T11; R7 de `alineacion-estrategica`, tarea 7).

Envuelve `report_serde.report_to_dict`/`report_from_dict` (ui/, T10 no se toca) y añade
las claves `semantic_filter_applied` y `strategic_alignment`. Vive en `llm/` — no en
`ui/report_serde.py` — para que `report_serde.py` siga sin conocer `llm/` ni
`AlineacionEstrategica` (Opción B, decisión #8, intacta): es esta capa, no la del
investigador ni la de serialización base, la que sabe que el filtro y la alineación
estratégica existen.
"""

from __future__ import annotations

from dataclasses import asdict

from agente_ong.llm.enrichment import EnrichedReport
from agente_ong.research.alignment import AlineacionEstrategica
from agente_ong.research.models import ResearchReport
from agente_ong.ui.report_serde import report_from_dict, report_to_dict


def enriched_report_to_dict(enriched: EnrichedReport) -> dict:
    """Serializa un `EnrichedReport` a un dict apto para JSON (tipos primitivos)."""
    data = report_to_dict(enriched.base)
    data["semantic_filter_applied"] = enriched.semantic_filter_applied
    data["strategic_alignment"] = {
        url: asdict(alineacion) for url, alineacion in enriched.strategic_alignment.items()
    }
    return data


def enriched_report_from_dict(data: dict) -> EnrichedReport:
    """Reconstruye un `EnrichedReport` desde el dict producido por `enriched_report_to_dict`.

    Retrocompatible con informes pre-R7 (persistidos antes de este cableado): sin las
    claves `semantic_filter_applied`/`strategic_alignment`, `.get(..., ...)` las trata
    como si el filtro/la extracción nunca se hubieran aplicado — mismo patrón que
    `result_type`/R20 en `report_serde.py`.
    """
    base: ResearchReport = report_from_dict(data)
    return EnrichedReport(
        base=base,
        semantic_filter_applied=data.get("semantic_filter_applied", False),
        strategic_alignment={
            url: AlineacionEstrategica(**valores)
            for url, valores in data.get("strategic_alignment", {}).items()
        },
    )
