"""Orquestación del filtro semántico sobre un ResearchReport ya construido (R7, T10).

Capa aditiva y externa a `research/`: `EnrichedReport` envuelve un `ResearchReport` sin
mutarlo ni tocar ningún tipo de `research/models.py` (Opción B, decisión #8 de T8, intacta
— ver design.md de `integracion-llm`). Degradación silenciosa: sin proveedor LLM
disponible, el informe original pasa intacto y sin clasificar.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from agente_ong.llm.filter_report import classify_report
from agente_ong.llm.provider import LLMProvider
from agente_ong.research.models import ResearchReport
from agente_ong.research.urlnorm import normalize_url


@dataclass
class EnrichedReport:
    """`ResearchReport` con clasificación semántica opcional aplicada.

    `base.opportunities` conserva TODAS las oportunidades (activas y descartadas): la
    separación para mostrar es responsabilidad de la capa de presentación
    (`ui/report_serde.py::classify_for_display`, spec `descartados-filtro`), no de esta
    capa de orquestación.
    """

    base: ResearchReport
    semantic_filter_applied: bool


def enrich_report(report: ResearchReport, provider: LLMProvider | None) -> EnrichedReport:
    """Clasifica `report.opportunities` con `provider` si está disponible.

    Sin `provider` (Ollama no disponible, R7.3): `report` pasa intacto como `base` (mismo
    objeto, no se clona), `semantic_filter_applied=False` — degradación 100% silenciosa.

    Con `provider`: usa `classify_report` (T8, no se toca) para clasificar cada
    oportunidad; construye `filter_verdicts` (clave = URL normalizada con `normalize_url`,
    valor = veredicto) y lo adjunta a `base` mediante `dataclasses.replace(report,
    filter_verdicts=verdicts)` — `report.opportunities` NUNCA se filtra ni se muta, el
    resto de campos del informe se preservan tal cual.
    """
    if provider is None:
        return EnrichedReport(base=report, semantic_filter_applied=False)

    classifications = classify_report(provider, report)
    verdicts = {
        normalize_url(opp.url.value or ""): classifications[id(opp)]
        for opp in report.opportunities
        if id(opp) in classifications
    }
    return EnrichedReport(
        base=replace(report, filter_verdicts=verdicts),
        semantic_filter_applied=True,
    )
