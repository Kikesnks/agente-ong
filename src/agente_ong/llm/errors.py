"""Errores propios del módulo LLM y reintentos para fallos transitorios (R4).

Cada adaptador (Claude/OpenAI/Ollama, T3/T4) traduce las excepciones específicas de su SDK
a uno de estos tipos — ningún consumidor de `LLMProvider` ve nunca una excepción cruda de
LangChain (R4.1).

Reintentos (R4.2, Opción A de T2): se reutiliza `with_retry` de
`research/sources/base.py` sin duplicar la lógica de backoff ni tocar `research/`.
`with_llm_retry` es un envoltorio fino que fija qué excepción es reintentable
(`LLMConnectionError`, transitoria). `LLMAuthError` nunca se reintenta (R4.3, no es
transitoria).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from agente_ong.research.sources.base import with_retry

T = TypeVar("T")


class LLMError(Exception):
    """Error base de la capa LLM."""


class LLMConnectionError(LLMError):
    """Fallo de red u otro error transitorio al llamar al proveedor de LLM."""


class LLMAuthError(LLMError):
    """Clave de API inválida o ausente. No es transitoria: nunca se reintenta."""


class LLMNoResponseError(LLMError):
    """El proveedor no devolvió una respuesta útil (p.ej. timeout tras reintentos)."""


def with_llm_retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Reintenta `func` ante `LLMConnectionError`, con el mismo backoff que `with_retry`.

    Envoltorio sobre `research.sources.base.with_retry` (Opción A: no se duplica la lógica
    de backoff, `research/` no se toca). Solo `LLMConnectionError` es reintentable —
    `LLMAuthError` y `LLMNoResponseError` no son transitorias y se propagan de inmediato.
    """
    return with_retry(
        func,
        attempts=attempts,
        base_delay=base_delay,
        exceptions=(LLMConnectionError,),
        sleep=sleep,
    )
