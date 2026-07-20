"""Parser de la respuesta cruda del LLM extractor de alineación estratégica (R5).

Frontera de validación entre la respuesta libre del LLM y la taxonomía cerrada de
`AlineacionEstrategica` (R1): valores fuera de catálogo u ODS fuera de rango se
descartan con log WARNING (nunca lanzan excepción); solo un JSON no parseable o con
estructura incorrecta lanza `AlignmentParseError`.
"""
from __future__ import annotations

import json
import logging

from agente_ong.research.alignment import AlineacionEstrategica
from agente_ong.research.catalogos_loader import (
    cargar_enfoques_transversales,
    cargar_prioridades_geograficas,
    cargar_sectores_plan_director,
)

logger = logging.getLogger(__name__)

_CAMPOS_ESPERADOS = (
    "ods",
    "prioridades_geograficas",
    "enfoques_transversales",
    "sectores_plan_director",
)

_ODS_MIN = 1
_ODS_MAX = 17


class AlignmentParseError(Exception):
    """La respuesta del LLM no es JSON parseable o no tiene la estructura esperada."""


def _quitar_code_fence(texto: str) -> str:
    """Si toda la respuesta (sin espacios sobrantes) está envuelta en un bloque de
    código Markdown, quita la línea de apertura (```` ``` `` o ```` ```json ````) y la
    de cierre (```` ``` ````). Si hay contenido antes o después del bloque no toca
    nada: deja que `json.loads` falle de forma natural, no intenta rescatar JSON
    embebido en texto libre.
    """
    texto = texto.strip()
    if not (texto.startswith("```") and texto.endswith("```")):
        return texto
    lineas = texto.splitlines()
    if len(lineas) < 2:
        return texto
    return "\n".join(lineas[1:-1]).strip()


def parsear_alineacion(respuesta_llm_cruda: str) -> AlineacionEstrategica:
    """Parsea la respuesta cruda del LLM extractor y valida los cuatro campos.

    - Valores fuera de catálogo se descartan con log WARNING.
    - ODS fuera del rango 1-17 se descartan con log WARNING.
    - Duplicados se colapsan preservando el orden de primera aparición.
    - JSON malformado o estructura incorrecta lanza `AlignmentParseError`.
    - Respuestas envueltas en un bloque de código Markdown (```json…``` o
      ```…```) se toleran: se quita la línea de apertura y la de cierre
      antes de parsear (algunos modelos locales, p.ej. qwen2.5:7b, ignoran la
      instrucción de "sin bloque de código" y envuelven el JSON siempre).
    - JSON parcial o vacío (p.ej. `{}`, o solo alguna de las cuatro claves) se
      tolera: las claves ausentes se rellenan con lista vacía, igual que si el
      LLM las hubiera devuelto explícitamente vacías (mismos modelos locales
      a veces colapsan a `{}` en vez de al esquema completo cuando no tienen
      nada que reportar).
    """
    try:
        data = json.loads(_quitar_code_fence(respuesta_llm_cruda))
    except json.JSONDecodeError as exc:
        raise AlignmentParseError(f"Respuesta del LLM no es JSON válido: {exc}") from exc

    if not isinstance(data, dict):
        raise AlignmentParseError(
            "Respuesta del LLM no tiene la estructura esperada: se esperaba un objeto JSON"
        )

    for campo in _CAMPOS_ESPERADOS:
        if campo not in data:
            data[campo] = []
            continue
        if not isinstance(data[campo], list):
            raise AlignmentParseError(
                f"Respuesta del LLM no tiene la estructura esperada: '{campo}' debe ser una lista"
            )

    return AlineacionEstrategica(
        ods=_filtrar_ods(data["ods"]),
        prioridades_geograficas=_filtrar_catalogo(
            data["prioridades_geograficas"],
            cargar_prioridades_geograficas(),
            "prioridades_geograficas",
        ),
        enfoques_transversales=_filtrar_catalogo(
            data["enfoques_transversales"],
            cargar_enfoques_transversales(),
            "enfoques_transversales",
        ),
        sectores_plan_director=_filtrar_catalogo(
            data["sectores_plan_director"],
            cargar_sectores_plan_director(),
            "sectores_plan_director",
        ),
    )


def _filtrar_ods(valores: list) -> list[int]:
    resultado: list[int] = []
    for valor in valores:
        if isinstance(valor, bool) or not isinstance(valor, int) or not (_ODS_MIN <= valor <= _ODS_MAX):
            logger.warning("ODS fuera de rango (%s-%s) descartado: %r", _ODS_MIN, _ODS_MAX, valor)
            continue
        if valor not in resultado:
            resultado.append(valor)
    return resultado


def _filtrar_catalogo(valores: list, catalogo: list[str], nombre_campo: str) -> list[str]:
    catalogo_valido = set(catalogo)
    resultado: list[str] = []
    for valor in valores:
        if not isinstance(valor, str) or valor not in catalogo_valido:
            logger.warning("Valor fuera de catálogo descartado en %s: %r", nombre_campo, valor)
            continue
        if valor not in resultado:
            resultado.append(valor)
    return resultado
