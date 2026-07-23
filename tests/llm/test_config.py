"""Tests de `LLMConfig`/`from_env()` (T5a de integracion-llm, reapertura 23-07-2026).

`build_provider`/`describe_llm_status` (T5b/T5c) no existen todavía en este módulo —
aquí solo se cubre la construcción de la configuración desde variables de entorno.
"""

from __future__ import annotations

from unittest.mock import patch

from agente_ong.llm.config import LLMConfig


def test_llm_config_defaults() -> None:
    config = LLMConfig()

    assert config.provider == "ollama"
    assert config.provider_explicit is True
    assert config.temperature == 0.0
    assert config.deepseek_api_key is None
    assert config.openai_api_key is None


def test_from_env_without_llm_provider_defaults_to_ollama(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    config = LLMConfig.from_env()

    assert config.provider == "ollama"
    assert config.provider_explicit is False


def test_from_env_with_llm_provider_deepseek(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    config = LLMConfig.from_env()

    assert config.provider == "deepseek"
    assert config.provider_explicit is True


def test_from_env_with_unrecognized_provider_value_is_kept_as_is(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "grok")

    config = LLMConfig.from_env()

    assert config.provider == "grok"
    assert config.provider_explicit is True


def test_from_env_without_paid_provider_keys_does_not_raise(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = LLMConfig.from_env()

    assert config.deepseek_api_key is None
    assert config.openai_api_key is None


def test_from_env_reads_paid_provider_keys_when_present(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    config = LLMConfig.from_env()

    assert config.deepseek_api_key == "sk-deepseek-test"
    assert config.openai_api_key == "sk-openai-test"


def test_from_env_without_llm_temperature_defaults_to_zero(monkeypatch) -> None:
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)

    config = LLMConfig.from_env()

    assert config.temperature == 0.0


def test_from_env_reads_llm_temperature_when_present(monkeypatch) -> None:
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")

    config = LLMConfig.from_env()

    assert config.temperature == 0.7


def test_from_env_with_invalid_llm_temperature_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("LLM_TEMPERATURE", "no-es-un-numero")

    config = LLMConfig.from_env()

    assert config.temperature == 0.0


def test_from_env_prefers_os_environ_over_dotenv_file(monkeypatch) -> None:
    """`override=False`: una variable ya presente en el proceso gana sobre el `.env`."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with patch("dotenv.load_dotenv") as mock_load_dotenv:
        config = LLMConfig.from_env()

    assert mock_load_dotenv.call_args.kwargs.get("override") is False
    assert config.provider == "openai"
    assert config.provider_explicit is True
