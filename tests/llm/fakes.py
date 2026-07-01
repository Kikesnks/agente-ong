"""Doble de prueba para `LLMProvider`.

`FakeLLMProvider` implementa el puerto con una respuesta fija e inyectable por
constructor, sin red ni SDK de proveedor — mismo patrón que `InMemoryStore` para
`ResearchStore` (adaptador mínimo y portátil, pensado para tests) y que `FakeSearchSource`
en `tests/research/fakes.py` (respuesta y fallo inyectables, llamadas registradas).
"""

from __future__ import annotations

from agente_ong.llm.provider import LLMProvider, LLMResponse


class FakeLLMProvider(LLMProvider):
    """Proveedor de LLM fake: devuelve una respuesta fija; opcionalmente falla."""

    def __init__(
        self,
        *,
        text: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        fail: BaseException | type[BaseException] | None = None,
    ) -> None:
        self._text = text
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._fail = fail
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        if self._fail is not None:
            raise self._fail if isinstance(self._fail, BaseException) else self._fail()
        return LLMResponse(
            text=self._text,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )
