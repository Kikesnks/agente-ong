"""Extracción de alineación estratégica para todo un `ResearchReport` (R7, tarea 7).

Mirror estructural de `filter_report.py::classify_report`: recorre
`report.opportunities` y aplica `extraer_alineacion` (tarea 6) SOLO a las
convocatorias con veredicto "si" del filtro semántico (relevantes). No necesita
try/except propio: `extraer_alineacion` ya atrapa `LLMError`/`AlignmentParseError`
internamente y devuelve `None` + log, nunca propaga una excepción.
"""
from __future__ import annotations

from agente_ong.llm.alignment_extractor import extraer_alineacion
from agente_ong.llm.filter_report import ClassificationResult
from agente_ong.llm.provider import LLMProvider
from agente_ong.research.alignment import AlineacionEstrategica
from agente_ong.research.models import GrantOpportunity, ResearchReport


def extraer_alineaciones_del_informe(
    provider: LLMProvider,
    report: ResearchReport,
    classifications: dict[int, ClassificationResult],
) -> dict[int, AlineacionEstrategica]:
    """Extrae la alineación estratégica de cada convocatoria relevante; clave = `id(opp)`.

    Una convocatoria sin veredicto "si" en `classifications` (descartada, no
    clasificada, o ausente) no se procesa: no se llama al LLM para ella (R7.2). Si
    `extraer_alineacion` devuelve `None` (Ollama caído a media ejecución, fallo de
    la llamada o respuesta malformada), esa convocatoria simplemente no aparece en
    el resultado — el caller trata "ausente" como alineación vacía.
    """
    resultados: dict[int, AlineacionEstrategica] = {}
    for opportunity in report.opportunities:
        if classifications.get(id(opportunity)) != "si":
            continue
        texto = _construir_texto(opportunity)
        alineacion = extraer_alineacion(texto, provider, opportunity_id=opportunity.url.value)
        if alineacion is not None:
            resultados[id(opportunity)] = alineacion
    return resultados


def _construir_texto(opportunity: GrantOpportunity) -> str:
    """Texto de la convocatoria para el extractor: título + los mismos campos que
    ya usa `filter_report._extract_snippet` para el filtro semántico."""
    fields = (
        ("Título", opportunity.title.value),
        ("Organismo", opportunity.organism.value),
        ("Ámbito", opportunity.scope.value),
        ("Importe", opportunity.amount.value),
        ("Plazo", opportunity.deadline.value),
    )
    return " | ".join(f"{label}: {value}" for label, value in fields if value)
