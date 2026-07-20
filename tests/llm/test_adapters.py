"""Tests de contrato de los adaptadores de `LLMProvider` (R2).

Parametrizado sobre los proveedores reales, con la capa LangChain mockeada (sin red real
— la verificación en vivo contra Ollama ya se hizo aparte, fuera de la suite).
`OpenAICompatibleProvider` (reapertura de SPEC 2, T4) se añadió a `ADAPTERS` para correr
el mismo test de contrato; Claude sigue aplazado (protocolo distinto, no
OpenAI-compatible).
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import ollama
import pytest
from langchain_core.messages import AIMessage
from openai import APIConnectionError, AuthenticationError, InternalServerError

from agente_ong.llm.adapters.ollama import OllamaProvider
from agente_ong.llm.adapters.openai_compatible import OpenAICompatibleProvider
from agente_ong.llm.errors import LLMAuthError, LLMConnectionError, LLMNoResponseError
from agente_ong.llm.provider import LLMProvider, LLMResponse

_OLLAMA_CHAT_MODEL = "agente_ong.llm.adapters.ollama.ChatOllama"
_OPENAI_COMPATIBLE_CHAT_MODEL = "agente_ong.llm.adapters.openai_compatible.ChatOpenAI"


def _build_ollama_provider() -> OllamaProvider:
    return OllamaProvider(model="qwen2.5:7b")


def _build_openai_compatible_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key="clave-de-prueba",
    )


def _httpx_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.deepseek.com/chat/completions")


def _httpx_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_httpx_request(), json={"error": {"message": "fallo"}})


# (factory del adaptador, ruta del ChatModel de LangChain a mockear)
ADAPTERS = [
    (_build_ollama_provider, _OLLAMA_CHAT_MODEL),
    (_build_openai_compatible_provider, _OPENAI_COMPATIBLE_CHAT_MODEL),
]


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


# --- Traducción de excepciones específica de OpenAICompatibleProvider (R4.1) ---


def test_openai_compatible_connection_failure_translates_to_llm_connection_error() -> None:
    with patch(_OPENAI_COMPATIBLE_CHAT_MODEL) as mock_chat_model:
        mock_chat_model.return_value.invoke.side_effect = APIConnectionError(request=_httpx_request())
        provider = _build_openai_compatible_provider()

        with pytest.raises(LLMConnectionError):
            provider.complete("system", "user")


def test_openai_compatible_authentication_error_translates_to_llm_auth_error() -> None:
    with patch(_OPENAI_COMPATIBLE_CHAT_MODEL) as mock_chat_model:
        mock_chat_model.return_value.invoke.side_effect = AuthenticationError(
            "clave inválida", response=_httpx_response(401), body=None
        )
        provider = _build_openai_compatible_provider()

        with pytest.raises(LLMAuthError):
            provider.complete("system", "user")


def test_openai_compatible_other_api_error_translates_to_llm_no_response_error() -> None:
    with patch(_OPENAI_COMPATIBLE_CHAT_MODEL) as mock_chat_model:
        mock_chat_model.return_value.invoke.side_effect = InternalServerError(
            "error interno del servidor", response=_httpx_response(500), body=None
        )
        provider = _build_openai_compatible_provider()

        with pytest.raises(LLMNoResponseError):
            provider.complete("system", "user")
