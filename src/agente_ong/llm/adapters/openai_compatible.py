"""Adaptador genérico OpenAI-compatible (`OpenAICompatibleProvider`) para el puerto
`LLMProvider` (R2, reapertura de SPEC 2 — T4).

Usa `ChatOpenAI` de `langchain-openai` internamente, con `base_url` inyectable: sirve
tanto para OpenAI mismo como para cualquier proveedor que hable el mismo formato de API
(verificado contra la documentación oficial de DeepSeek — `https://api.deepseek.com`,
endpoint `/chat/completions`, mismo formato de mensajes `role`/`content` y de respuesta
`choices[0].message.content` + `usage.prompt_tokens`/`completion_tokens`; la propia
documentación de DeepSeek instruye a usar el SDK de `openai` sin modificar salvo
`base_url`/`api_key`).

`base_url`, `api_key` y `model` son obligatorios (a diferencia de Ollama, local y sin
clave): no hay `base_url` por defecto para evitar apuntar sin querer al proveedor de
pago equivocado.

Mapeo de la respuesta: igual que `ollama.py` (`response.content` -> texto,
`response.usage_metadata` -> tokens; misma forma estandarizada por LangChain).

Traducción de excepciones basada en la jerarquía DOCUMENTADA de `openai-python`
(`openai._exceptions`), NO verificada en vivo contra una respuesta real (sin clave de
API disponible todavía): `APIConnectionError` (cubre `APITimeoutError`, que hereda de
ella) -> transitorio; `AuthenticationError` -> no transitorio, clave inválida; cualquier
otro `OpenAIError` -> respuesta no útil. Antes de confiar en esto en producción, repetir
la verificación en vivo que ya se hizo para Ollama (T3) en cuanto haya
`DEEPSEEK_API_KEY` real (ver decisión #11 de `decisiones_pendientes.md`).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, AuthenticationError, OpenAIError

from agente_ong.llm.errors import LLMAuthError, LLMConnectionError, LLMNoResponseError
from agente_ong.llm.provider import LLMProvider, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    """Adaptador de `LLMProvider` sobre cualquier API compatible con el formato OpenAI."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0.0,
    ) -> None:
        self._client = ChatOpenAI(
            model=model, base_url=base_url, api_key=api_key, temperature=temperature
        )

    def complete(self, system: str, user: str) -> LLMResponse:
        try:
            response = self._client.invoke(
                [SystemMessage(content=system), HumanMessage(content=user)]
            )
        except AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except APIConnectionError as exc:
            # Fallo de red/transporte (conexión rechazada, timeout...): transitorio.
            raise LLMConnectionError(str(exc)) from exc
        except OpenAIError as exc:
            # El servidor respondió pero con un error no de autenticación ni de red
            # (límite de tasa, error interno...): no es un problema de red reintentable
            # sin más, sino de respuesta útil.
            raise LLMNoResponseError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - ninguna excepción cruda escapa (R4.1)
            raise LLMNoResponseError(str(exc)) from exc

        usage = response.usage_metadata or {}
        return LLMResponse(
            text=response.content,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
