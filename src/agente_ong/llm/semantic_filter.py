"""Filtro semántico mínimo (R6, Opción 1): clasifica un resultado como convocatoria
abierta o no, mediante una pregunta binaria al LLM.

`classify_result` arma el prompt (system cargado desde archivo, T6; user con los datos
concretos del resultado) y traduce la respuesta del modelo a un booleano fiable, con una
tercera salida `"no_clasificado"` cuando la respuesta no es interpretable como SI/NO
(R6.3/R6.4) — nunca se fuerza un valor por defecto.
"""

from __future__ import annotations

from typing import Literal

from agente_ong.llm.prompt_loader import load_prompt
from agente_ong.llm.provider import LLMProvider

ClassificationResult = Literal["si", "no", "no_clasificado"]


def classify_result(provider: LLMProvider, title: str, snippet: str) -> ClassificationResult:
    """Clasifica un resultado de búsqueda como convocatoria abierta: "si"/"no"/"no_clasificado".

    Propaga tal cual cualquier excepción de `provider.complete` (`LLMConnectionError`,
    `LLMAuthError`, `LLMNoResponseError`...) — la gestión de fallos por resultado es
    responsabilidad de la integración con el investigador (T8), no de esta función.
    """
    system = load_prompt("semantic_filter")
    user = f"Título: {title}\nExtracto: {snippet}"
    response = provider.complete(system, user)

    normalized = response.text.strip().upper()
    if normalized == "SI":
        return "si"
    if normalized == "NO":
        return "no"
    return "no_clasificado"
