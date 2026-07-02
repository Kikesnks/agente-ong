"""Tests de contrato de los adaptadores de `LLMProvider` (R2).

Parametrizado sobre los proveedores reales, con la capa LangChain mockeada (sin red real
— la verificación en vivo contra Ollama ya se hizo aparte, fuera de la suite). T4 añadirá
Claude y OpenAI a `ADAPTERS` para que corran el mismo test de contrato.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import ollama
import pytest
from langchain_core.messages import AIMessage

from agente_ong.llm.adapters.ollama import OllamaProvider
from agente_ong.llm.errors import LLMConnectionError, LLMNoResponseError
from agente_ong.llm.provider import LLMProvider, LLMResponse

_OLLAMA_CHAT_MODEL = "agente_ong.llm.adapters.ollama.ChatOllama"


def _build_ollama_provider() -> OllamaProvider:
    return OllamaProvider(model="qwen2.5:7b")


# (factory del adaptador, ruta del ChatModel de LangChain a mockear)
ADAPTERS = [(_build_ollama_provider, _OLLAMA_CHAT_MODEL)]


# --- Contrato compartido (R2.1/R2.2/R2.3) ---


@pytest.mark.parametrize("build_provider, chat_model_path", ADAPTERS)
def test_adapter_implements_the_port(build_provider, chat_model_path) -> None:
    with patch(chat_model_path):
        provider = build_provider()
    assert isinstance(provider, LLMProvider)


@pytest.mark.parametrize("build_provider, chat_model_path", ADAPTERS)
def test_construction_without_api_key_does_not_fail(build_provider, chat_model_path) -> None:
    # Ollama es local: no requiere clave (R2.3). Construir no debe intentar red ni fallar.
    with patch(chat_model_path) as mock_chat_model:
        build_provider()
    mock_chat_model.assert_called_once()


@pytest.mark.parametrize("build_provider, chat_model_path", ADAPTERS)
def test_complete_returns_llmresponse_with_text_and_nonnegative_tokens(
    build_provider, chat_model_path
) -> None:
    fake_response = AIMessage(
        content="SI",
        usage_metadata={"input_tokens": 35, "output_tokens": 2, "total_tokens": 37},
    )
    with patch(chat_model_path) as mock_chat_model:
        mock_chat_model.return_value.invoke.return_value = fake_response
        provider = build_provider()
        response = provider.complete("system prompt", "user prompt")

    assert isinstance(response, LLMResponse)
    assert response.text == "SI"
    assert response.input_tokens == 35
    assert response.output_tokens == 2
    assert response.input_tokens >= 0
    assert response.output_tokens >= 0


@pytest.mark.parametrize("build_provider, chat_model_path", ADAPTERS)
def test_complete_defaults_tokens_to_zero_when_usage_metadata_missing(
    build_provider, chat_model_path
) -> None:
    fake_response = AIMessage(content="NO", usage_metadata=None)
    with patch(chat_model_path) as mock_chat_model:
        mock_chat_model.return_value.invoke.return_value = fake_response
        provider = build_provider()
        response = provider.complete("system", "user")

    assert response.text == "NO"
    assert response.input_tokens == 0
    assert response.output_tokens == 0


# --- Traducción de excepciones específica de Ollama (R4.1) ---


def test_ollama_connection_failure_translates_to_llm_connection_error() -> None:
    with patch(_OLLAMA_CHAT_MODEL) as mock_chat_model:
        mock_chat_model.return_value.invoke.side_effect = httpx.ConnectError("conexion rechazada")
        provider = OllamaProvider(model="qwen2.5:7b")

        with pytest.raises(LLMConnectionError):
            provider.complete("system", "user")


def test_ollama_response_error_translates_to_llm_no_response_error() -> None:
    with patch(_OLLAMA_CHAT_MODEL) as mock_chat_model:
        mock_chat_model.return_value.invoke.side_effect = ollama.ResponseError("modelo no encontrado")
        provider = OllamaProvider(model="qwen2.5:7b")

        with pytest.raises(LLMNoResponseError):
            provider.complete("system", "user")
