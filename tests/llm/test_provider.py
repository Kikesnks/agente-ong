"""Tests del puerto `LLMProvider` (R1: contrato único e independiente de proveedor)."""

from __future__ import annotations

import ast
import inspect

from agente_ong.llm import provider
from agente_ong.llm.provider import LLMProvider, LLMResponse
from llm.fakes import FakeLLMProvider


def test_fake_llm_provider_implements_the_port() -> None:
    fake = FakeLLMProvider(text="ok", input_tokens=1, output_tokens=1)
    assert isinstance(fake, LLMProvider)


def test_complete_returns_response_with_text_and_nonnegative_tokens() -> None:
    fake = FakeLLMProvider(text="respuesta", input_tokens=12, output_tokens=3)

    response = fake.complete("system prompt", "user prompt")

    assert isinstance(response, LLMResponse)
    assert isinstance(response.text, str)
    assert response.text == "respuesta"
    assert response.input_tokens >= 0
    assert response.output_tokens >= 0
    assert (response.input_tokens, response.output_tokens) == (12, 3)
    assert fake.calls == [("system prompt", "user prompt")]


def test_provider_module_has_no_langchain_import() -> None:
    # R1.2: nada fuera de los adaptadores importa LangChain — provider.py es puro stdlib.
    tree = ast.parse(inspect.getsource(provider))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
    assert not any("langchain" in name for name in imported_names)
