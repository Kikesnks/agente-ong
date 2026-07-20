"""Extractor LLM de alineación estratégica (R7): construye el prompt de
`opportunity_alignment.md` (tarea 5) con la taxonomía inyectada, llama al proveedor y
pasa la respuesta al parser (`alignment_parser.py`, tarea 4).

Degradación por convocatoria, no por run completo: a diferencia de `enrich_report`
(degradación 100% silenciosa), aquí SÍ se registra en el log —WARNING si no hay
proveedor disponible, ERROR si falla la llamada o el parseo— por requisito explícito de
R7; el retorno es `None` en los tres casos, y es la integración en el pipeline (tarea 7)
la que decide qué hacer con ese `None` (los cuatro campos quedan `[]`).
"""
from __future__ import annotations

import logging
from pathlib import Path

from agente_ong.llm.errors import LLMError
from agente_ong.llm.prompt_loader import load_prompt
from agente_ong.llm.provider import LLMProvider
from agente_ong.research.alignment import AlineacionEstrategica
from agente_ong.research.alignment_parser import AlignmentParseError, parsear_alineacion
from agente_ong.research.catalogos_loader import (
    cargar_enfoques_transversales,
    cargar_prioridades_geograficas,
    cargar_sectores_plan_director,
)
from agente_ong.research.ods_catalogo import load_ods_catalogo

logger = logging.getLogger(__name__)

_ODS_CATALOGO_PATH = Path(__file__).resolve().parent.parent / "research" / "ods_catalogo.yaml"


def _renderizar_ods() -> str:
    entradas = load_ods_catalogo(_ODS_CATALOGO_PATH)
    return "\n".join(f"{entrada['numero']}. {entrada['nombre']}" for entrada in entradas)


def _renderizar_lista(valores: list[str]) -> str:
    return "\n".join(f"- {valor}" for valor in valores)


def _construir_system_prompt() -> str:
    plantilla = load_prompt("opportunity_alignment")
    return (
        plantilla.replace("<<ODS>>", _renderizar_ods())
        .replace("<<PRIORIDADES_GEOGRAFICAS>>", _renderizar_lista(cargar_prioridades_geograficas()))
        .replace("<<ENFOQUES_TRANSVERSALES>>", _renderizar_lista(cargar_enfoques_transversales()))
        .replace("<<SECTORES_PLAN_DIRECTOR>>", _renderizar_lista(cargar_sectores_plan_director()))
    )


def _sufijo_id(opportunity_id: str | None) -> str:
    return f" ({opportunity_id})" if opportunity_id else ""


def extraer_alineacion(
    opportunity_text: str,
    provider: LLMProvider | None,
    *,
    opportunity_id: str | None = None,
) -> AlineacionEstrategica | None:
    """Ejecuta la extracción de alineación estratégica llamando al LLM.

    Devuelve `None` si Ollama no está disponible (`provider is None`), si la llamada al
    LLM falla, o si el parser lanza `AlignmentParseError`. El caller (tarea 7) convierte
    `None` a `[]` en los cuatro campos de alineación de la convocatoria.
    """
    if provider is None:
        logger.warning("Ollama no disponible: extracción de alineación omitida%s", _sufijo_id(opportunity_id))
        return None

    system = _construir_system_prompt()
    try:
        response = provider.complete(system, opportunity_text)
    except LLMError as exc:
        logger.error(
            "Fallo en la llamada LLM de extracción de alineación%s: %s: %s",
            _sufijo_id(opportunity_id),
            type(exc).__name__,
            exc,
        )
        return None

    try:
        return parsear_alineacion(response.text)
    except AlignmentParseError as exc:
        logger.error(
            "Fallo al parsear la respuesta LLM de alineación%s: %s",
            _sufijo_id(opportunity_id),
            exc,
        )
        return None
