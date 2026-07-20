"""Orquestación del filtro semántico y de la extracción de alineación estratégica sobre
un ResearchReport ya construido (R7 de `integracion-llm`, T10; R7 de
`alineacion-estrategica`, tarea 7).

Capa aditiva y externa a `research/`: `EnrichedReport` envuelve un `ResearchReport` sin
mutarlo ni tocar ningún tipo de `research/models.py` (Opción B, decisión #8 de T8, intacta
— ver design.md de `integracion-llm`; la misma decisión se reafirmó explícitamente para
`strategic_alignment` en la tarea 3 de `alineacion-estrategica`: no se añade ningún campo
a `research/models.py`, aunque `filter_verdicts` sí viva allí como precedente anterior a
esa decisión). Degradación silenciosa: sin proveedor LLM disponible, el informe original
pasa intacto y sin clasificar ni alinear.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from agente_ong.llm.alignment_report import extraer_alineaciones_del_informe
from agente_ong.llm.filter_report import classify_report
from agente_ong.llm.provider import LLMProvider
from agente_ong.research.alignment import AlineacionEstrategica
from agente_ong.research.models import ResearchReport
from agente_ong.research.urlnorm import normalize_url


@dataclass
class EnrichedReport:
    """`ResearchReport` con clasificación semántica y alineación estratégica opcionales.

    `base.opportunities` conserva TODAS las oportunidades (activas y descartadas): la
    separación para mostrar es responsabilidad de la capa de presentación
    (`ui/report_serde.py::classify_for_display`, spec `descartados-filtro`), no de esta
    capa de orquestación. `strategic_alignment` (clave = URL normalizada) solo tiene
    entrada para las convocatorias relevantes con extracción exitosa; su ausencia
    equivale a alineación vacía (`[]` en los cuatro campos).
    """

    base: ResearchReport
    semantic_filter_applied: bool
    strategic_alignment: dict[str, AlineacionEstrategica] = field(default_factory=dict)


def enrich_report(report: ResearchReport, provider: LLMProvider | None) -> EnrichedReport:
    """Clasifica y alinea estratégicamente `report.opportunities` con `provider` si está disponible.

    Sin `provider` (Ollama no disponible, R7.3 de `integracion-llm` / R7.4 de
    `alineacion-estrategica`): `report` pasa intacto como `base` (mismo objeto, no se
    clona), `semantic_filter_applied=False`, `strategic_alignment={}` — degradación 100%
    silenciosa.

    Con `provider`: usa `classify_report` (T8, no se toca) para clasificar cada
    oportunidad; construye `filter_verdicts` (clave = URL normalizada con `normalize_url`,
    valor = veredicto) y lo adjunta a `base` mediante `dataclasses.replace(report,
    filter_verdicts=verdicts)` — `report.opportunities` NUNCA se filtra ni se muta, el
    resto de campos del informe se preservan tal cual. Además usa
    `extraer_alineaciones_del_informe` (tarea 7 de `alineacion-estrategica`) con los
    mismos `classifications` ya calculados, para no repetir la llamada de clasificación.
    """
    if provider is None:
        return EnrichedReport(base=report, semantic_filter_applied=False, strategic_alignment={})

    classifications = classify_report(provider, report)
    verdicts = {
        normalize_url(opp.url.value or ""): classifications[id(opp)]
        for opp in report.opportunities
        if id(opp) in classifications
    }
    alineaciones = extraer_alineaciones_del_informe(provider, report, classifications)
    strategic_alignment = {
        normalize_url(opp.url.value or ""): alineaciones[id(opp)]
        for opp in report.opportunities
        if id(opp) in alineaciones
    }
    return EnrichedReport(
        base=replace(report, filter_verdicts=verdicts),
        semantic_filter_applied=True,
        strategic_alignment=strategic_alignment,
    )
