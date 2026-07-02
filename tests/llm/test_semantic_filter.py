"""Tests de `classify_result` (R6.3/R6.4): traducción de la respuesta del LLM a
"si"/"no"/"no_clasificado", y propagación de errores del proveedor (T8 los gestiona)."""

from __future__ import annotations

import pytest

from agente_ong.llm.errors import LLMConnectionError
from agente_ong.llm.prompt_loader import load_prompt
from agente_ong.llm.semantic_filter import classify_result
from llm.fakes import FakeLLMProvider


# --- Interpretación exacta ---


def test_classify_result_si() -> None:
    fake = FakeLLMProvider(text="SI")
    assert classify_result(fake, "Convocatoria X", "Plazo abierto hasta diciembre") == "si"


def test_classify_result_no() -> None:
    fake = FakeLLMProvider(text="NO")
    assert classify_result(fake, "Noticia sobre cooperación", "Resumen del artículo") == "no"


# --- Normalización (espacios/mayúsculas, nunca acentos ni contenido extra) ---


@pytest.mark.parametrize("raw", ["  si  ", "Si", "SI\n", "  SI"])
def test_classify_result_normalizes_whitespace_and_case_to_si(raw: str) -> None:
    fake = FakeLLMProvider(text=raw)
    assert classify_result(fake, "Título", "Extracto") == "si"


@pytest.mark.parametrize("raw", ["  no  ", "No", "NO\n", "  NO"])
def test_classify_result_normalizes_whitespace_and_case_to_no(raw: str) -> None:
    fake = FakeLLMProvider(text=raw)
    assert classify_result(fake, "Título", "Extracto") == "no"


# --- "no_clasificado": nunca se fuerza SI/NO por defecto ---


@pytest.mark.parametrize(
    "raw",
    [
        "SI, es una convocatoria abierta con plazo hasta diciembre",
        "",
        "   ",
        "???",
        "N/A",
        "Sí",  # con tilde: strip().upper() da "SÍ", no coincide exacto con "SI"
    ],
)
def test_classify_result_defaults_to_no_clasificado(raw: str) -> None:
    fake = FakeLLMProvider(text=raw)
    assert classify_result(fake, "Título", "Extracto") == "no_clasificado"


# --- Prompt enviado al proveedor ---


def test_system_prompt_sent_matches_the_loaded_prompt() -> None:
    fake = FakeLLMProvider(text="SI")

    classify_result(fake, "Título", "Extracto")

    assert len(fake.calls) == 1
    system_sent, _ = fake.calls[0]
    assert system_sent == load_prompt("semantic_filter")


def test_user_prompt_contains_title_and_snippet() -> None:
    fake = FakeLLMProvider(text="NO")

    classify_result(fake, "Convocatoria de ejemplo", "Plazo: 31 de diciembre")

    _, user_sent = fake.calls[0]
    assert "Convocatoria de ejemplo" in user_sent
    assert "Plazo: 31 de diciembre" in user_sent


# --- Propagación de errores del proveedor (sin capturarlos, T8 los gestiona) ---


def test_provider_exception_propagates_without_being_caught() -> None:
    fake = FakeLLMProvider(fail=LLMConnectionError("red caida"))

    with pytest.raises(LLMConnectionError):
        classify_result(fake, "Título", "Extracto")
