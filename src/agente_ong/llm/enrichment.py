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
from agente_ong.research.models import GrantOpportunity, ResearchReport


@dataclass
class EnrichedReport:
    """`ResearchReport` con clasificación semántica opcional aplicada.

    `base` es el informe a mostrar (con `opportunities` ya sin los descartados/no
    clasificados cuando el filtro se aplicó); `discarded`/`unclassified` conservan esas
    oportunidades por separado — nunca se ocultan (R7.4).
    """

    base: ResearchReport
    discarded: list[GrantOpportunity]
    unclassified: list[GrantOpportunity]
    semantic_filter_applied: bool


def enrich_report(report: ResearchReport, provider: LLMProvider | None) -> EnrichedReport:
    """Clasifica `report.opportunities` con `provider` si está disponible.

    Sin `provider` (Ollama no disponible, R7.3): `report` pasa intacto como `base` (mismo
    objeto, no se clona), buckets vacíos, `semantic_filter_applied=False` — degradación
    100% silenciosa.

    Con `provider`: usa `classify_report` (T8, no se toca) para clasificar cada
    oportunidad; separa `report.opportunities` en kept/discarded/unclassified por
    identidad (`id(opportunity)`, misma clave que usa `classify_report`); construye `base`
    con `dataclasses.replace(report, opportunities=kept)` — el resto de campos del informe
    (`ledger`, `failed_sources`, etc.) se preservan tal cual, y `report` NUNCA se muta. Un
    fallo de clasificación (`LLMError`) por oportunidad ya queda como `"no_clasificado"` en
    el dict que devuelve `classify_report` (con su propio `logger.warning`) — aquí solo se
    rutea al bucket correcto, no se vuelve a atrapar la excepción.
    """
    if provider is None:
        return EnrichedReport(
            base=report,
            discarded=[],
            unclassified=[],
            semantic_filter_applied=False,
        )

    classifications = classify_report(provider, report)

    kept: list[GrantOpportunity] = []
    discarded: list[GrantOpportunity] = []
    unclassified: list[GrantOpportunity] = []
    for opportunity in report.opportunities:
        result = classifications.get(id(opportunity), "no_clasificado")
        if result == "si":
            kept.append(opportunity)
        elif result == "no":
            discarded.append(opportunity)
        else:
            unclassified.append(opportunity)

    return EnrichedReport(
        base=replace(report, opportunities=kept),
        discarded=discarded,
        unclassified=unclassified,
        semantic_filter_applied=True,
    )
