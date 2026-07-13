"""Integración del filtro semántico con los resultados del investigador (T8, Opción B).

`classify_report` recorre `report.opportunities` TAL CUAL las construyó el investigador
(sin ordenar, filtrar ni copiar — misma advertencia que ya documenta R14/UI-34 en
`ui/report_serde.py::opportunity_numbers`: `id()` deja de ser válido si los objetos se
copian) y clasifica CADA una con `classify_result` de `semantic_filter` (T7), Opción 1:
todas, sin enrutado por `result_type`.

Capa aditiva: `research/models.py` se LEE (`ResearchReport`, `GrantOpportunity`) pero
nunca se modifica — ni `result_type` ni ningún otro campo. La marca de clasificación vive
en el `dict` que devuelve esta función, propio de `llm/` (Opción B).
"""

from __future__ import annotations

import logging
from typing import Literal

from agente_ong.llm.errors import LLMError
from agente_ong.llm.provider import LLMProvider
from agente_ong.llm.semantic_filter import classify_result
from agente_ong.research.models import GrantOpportunity, ResearchReport

logger = logging.getLogger(__name__)

ClassificationResult = Literal["si", "no", "no_clasificado_provider", "no_clasificado_response"]


def classify_report(
    provider: LLMProvider, report: ResearchReport
) -> dict[int, ClassificationResult]:
    """Clasifica cada oportunidad de `report.opportunities`; clave = `id(opportunity)`.

    Modo "training": `report.opportunities` es `[]` por diseño (`verify()` recolecta
    `resources` vía `TrainingCollector`, no construye `opportunities` — ver R23.3/decisión
    #4 de `investigador-v2`). No es un caso especial: el bucle no itera nada, el provider
    no se llama, y se devuelve `{}`.

    Un fallo de clasificación (`LLMError` y sus subclases: conexión, autenticación, sin
    respuesta) en una oportunidad no aborta el resto — se registra como aviso y esa
    oportunidad queda `"no_clasificado_provider"` (coherente con `failed_sources` del investigador:
    un fallo aislado no tumba el resto del procesamiento).
    """
    results: dict[int, ClassificationResult] = {}
    for opportunity in report.opportunities:
        title = opportunity.title.value or ""
        snippet = _extract_snippet(opportunity)
        try:
            results[id(opportunity)] = classify_result(provider, title, snippet)
        except LLMError as exc:
            url = opportunity.url.value or "url desconocida"
            logger.warning(
                "Fallo al clasificar oportunidad (%s): %s: %s",
                url,
                type(exc).__name__,
                exc,
            )
            results[id(opportunity)] = "no_clasificado_provider"
    return results


def _extract_snippet(opportunity: GrantOpportunity) -> str:
    """Construye el "extracto" del user prompt a partir de los `Claim` ya existentes.

    `GrantOpportunity` no tiene un campo `snippet` (a diferencia de `SearchHit`, que ya
    quedó agrupado en Claims verificados al llegar aquí). Se combinan los valores NO
    vacíos de organismo, ámbito, importe y plazo — el contenido más informativo ya
    presente en la convocatoria, sin inventar ni derivar ningún dato nuevo.
    """
    fields = (
        ("Organismo", opportunity.organism.value),
        ("Ámbito", opportunity.scope.value),
        ("Importe", opportunity.amount.value),
        ("Plazo", opportunity.deadline.value),
    )
    return " | ".join(f"{label}: {value}" for label, value in fields if value)
