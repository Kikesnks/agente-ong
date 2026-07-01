"""Tests de la jerarquía de errores propios del LLM y de los reintentos (R4)."""

from __future__ import annotations

import pytest

from agente_ong.llm.errors import (
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMNoResponseError,
    with_llm_retry,
)
from llm.fakes import FakeLLMProvider


def test_llm_error_hierarchy() -> None:
    assert issubclass(LLMError, Exception)
    assert issubclass(LLMConnectionError, LLMError)
    assert issubclass(LLMAuthError, LLMError)
    assert issubclass(LLMNoResponseError, LLMError)


def test_transient_failure_is_retried_and_eventually_succeeds() -> None:
    # Fallo transitorio simulado dos veces antes de que el proveedor (fake) responda bien.
    slept: list[float] = []
    calls = {"n": 0}
    fake = FakeLLMProvider(text="ok", input_tokens=1, output_tokens=1)

    def call() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise LLMConnectionError("red caida")
        return fake.complete("system", "user").text

    result = with_llm_retry(call, attempts=3, base_delay=1.0, sleep=slept.append)

    assert result == "ok"
    assert calls["n"] == 3
    assert slept == [1.0, 2.0]  # backoff exponencial: base_delay * 2**intento


def test_llm_auth_error_is_never_retried() -> None:
    fake = FakeLLMProvider(fail=LLMAuthError("clave invalida"))

    with pytest.raises(LLMAuthError):
        with_llm_retry(lambda: fake.complete("system", "user"), attempts=3, sleep=lambda _s: None)

    assert len(fake.calls) == 1  # sin reintentos: falla en el primer intento


def test_exhausted_retries_reraise_llm_connection_error_not_raw_exception() -> None:
    fake = FakeLLMProvider(fail=LLMConnectionError("red caida"))

    with pytest.raises(LLMConnectionError):
        with_llm_retry(lambda: fake.complete("system", "user"), attempts=2, sleep=lambda _s: None)

    assert len(fake.calls) == 2  # se agotaron los 2 intentos configurados
