"""Adaptador Ollama (`OllamaProvider`) para el puerto `LLMProvider` (R2).

Usa `ChatOllama` de `langchain-ollama` internamente. Proveedor local: sin clave de API
(R2.3), se construye solo con `model`/`base_url`/`temperature`.

Mapeo de la respuesta y traducción de excepciones fijados tras una verificación EN VIVO
contra `qwen2.5:7b` (mismo método que R17.3/R19.1/R23.6 de `investigador-v2`):

- `response.content` -> texto (`str` directo; `AIMessage.content`).
- `response.usage_metadata` -> `dict` con claves exactas `"input_tokens"`/
  `"output_tokens"` (`.get(..., 0)`: puede venir ausente o incompleto, nunca se inventa un
  valor de tokens).
"""

from __future__ import annotations

import httpx
import ollama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from agente_ong.llm.errors import LLMConnectionError, LLMNoResponseError
from agente_ong.llm.provider import LLMProvider, LLMResponse

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    """Adaptador de `LLMProvider` sobre un servidor Ollama local."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        temperature: float = 0.0,
    ) -> None:
        self._client = ChatOllama(model=model, base_url=base_url, temperature=temperature)

    def complete(self, system: str, user: str) -> LLMResponse:
        try:
            response = self._client.invoke(
                [SystemMessage(content=system), HumanMessage(content=user)]
            )
        except httpx.HTTPError as exc:
            # Fallo de red/transporte (conexión rechazada, timeout...): transitorio.
            raise LLMConnectionError(str(exc)) from exc
        except (ollama.ResponseError, ollama.RequestError) as exc:
            # El servidor respondió pero con un error (p.ej. modelo inexistente): no es
            # un problema de red reintentable sin más, sino de respuesta útil.
            raise LLMNoResponseError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - ninguna excepción cruda escapa (R4.1)
            raise LLMNoResponseError(str(exc)) from exc

        usage = response.usage_metadata or {}
        return LLMResponse(
            text=response.content,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
