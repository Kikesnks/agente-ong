"""Tests del cargador genérico de prompts (R6)."""

from __future__ import annotations

import pytest

from agente_ong.llm.prompt_loader import load_prompt

_QUESTION = "¿Es esto una convocatoria de subvención ABIERTA a la que una ONG puede presentarse?"


def test_load_prompt_semantic_filter_is_not_empty() -> None:
    content = load_prompt("semantic_filter")
    assert isinstance(content, str)
    assert content.strip() != ""


def test_load_prompt_semantic_filter_includes_the_exact_question() -> None:
    content = load_prompt("semantic_filter")
    assert _QUESTION in content


def test_load_prompt_semantic_filter_includes_output_format_instructions() -> None:
    content = load_prompt("semantic_filter")
    assert "SI" in content
    assert "NO" in content
    assert "sin explicación" in content


def test_load_prompt_missing_file_raises_file_not_found_error() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("no_existe")
