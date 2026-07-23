"""Tests de `LLMConfig`/`from_env()`/`build_provider`/`describe_llm_status` (T5a-T5c de
integracion-llm, reapertura 23-07-2026).
"""

from __future__ import annotations

from unittest.mock import patch

from agente_ong.llm.config import LLMConfig, build_provider, describe_llm_status


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


# --- build_provider (T5b) ---

_IS_OLLAMA_AVAILABLE = "agente_ong.llm.config.is_ollama_available"
_OLLAMA_PROVIDER = "agente_ong.llm.config.OllamaProvider"
_OPENAI_COMPATIBLE_PROVIDER = "agente_ong.llm.config.OpenAICompatibleProvider"


def test_build_provider_disabled_returns_none() -> None:
    config = LLMConfig(provider="disabled")

    assert build_provider(config) is None


def test_build_provider_ollama_available_returns_ollama_provider() -> None:
    config = LLMConfig(provider="ollama", temperature=0.5)

    with patch(_IS_OLLAMA_AVAILABLE, return_value=True), patch(
        _OLLAMA_PROVIDER
    ) as mock_ollama_provider:
        result = build_provider(config)

    mock_ollama_provider.assert_called_once_with(model="qwen2.5:7b", temperature=0.5)
    assert result is mock_ollama_provider.return_value


def test_build_provider_ollama_not_available_returns_none() -> None:
    config = LLMConfig(provider="ollama")

    with patch(_IS_OLLAMA_AVAILABLE, return_value=False), patch(
        _OLLAMA_PROVIDER
    ) as mock_ollama_provider:
        result = build_provider(config)

    assert result is None
    mock_ollama_provider.assert_not_called()


def test_build_provider_deepseek_with_key_returns_openai_compatible_provider() -> None:
    config = LLMConfig(
        provider="deepseek", deepseek_api_key="sk-deepseek-test", temperature=0.3
    )

    with patch(_OPENAI_COMPATIBLE_PROVIDER) as mock_provider:
        result = build_provider(config)

    mock_provider.assert_called_once_with(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key="sk-deepseek-test",
        temperature=0.3,
    )
    assert result is mock_provider.return_value


def test_build_provider_deepseek_without_key_returns_none() -> None:
    config = LLMConfig(provider="deepseek", deepseek_api_key=None)

    with patch(_OPENAI_COMPATIBLE_PROVIDER) as mock_provider:
        result = build_provider(config)

    assert result is None
    mock_provider.assert_not_called()


def test_build_provider_openai_with_key_returns_openai_compatible_provider() -> None:
    config = LLMConfig(
        provider="openai", openai_api_key="sk-openai-test", temperature=0.0
    )

    with patch(_OPENAI_COMPATIBLE_PROVIDER) as mock_provider:
        result = build_provider(config)

    mock_provider.assert_called_once_with(
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        api_key="sk-openai-test",
        temperature=0.0,
    )
    assert result is mock_provider.return_value


def test_build_provider_openai_without_key_returns_none() -> None:
    config = LLMConfig(provider="openai", openai_api_key=None)

    with patch(_OPENAI_COMPATIBLE_PROVIDER) as mock_provider:
        result = build_provider(config)

    assert result is None
    mock_provider.assert_not_called()


def test_build_provider_unrecognized_provider_returns_none() -> None:
    config = LLMConfig(provider="grok")

    assert build_provider(config) is None


def test_build_provider_never_raises_for_bogus_provider_values() -> None:
    for bogus in ("", "claude", "OLLAMA", " ollama", "Deepseek"):
        config = LLMConfig(provider=bogus)
        assert build_provider(config) is None


# --- describe_llm_status (T5c) ---


def test_describe_llm_status_disabled() -> None:
    config = LLMConfig(provider="disabled")

    provider, message, is_alarm = describe_llm_status(config)

    assert provider is None
    assert message == "filtro desactivado por configuración"
    assert is_alarm is True


def test_describe_llm_status_deepseek_without_key() -> None:
    config = LLMConfig(provider="deepseek", deepseek_api_key=None, provider_explicit=True)

    provider, message, is_alarm = describe_llm_status(config)

    assert provider is None
    assert message == "`deepseek` configurado pero falta `DEEPSEEK_API_KEY`"
    assert is_alarm is True


def test_describe_llm_status_openai_without_key() -> None:
    config = LLMConfig(provider="openai", openai_api_key=None, provider_explicit=True)

    provider, message, is_alarm = describe_llm_status(config)

    assert provider is None
    assert message == "`openai` configurado pero falta `OPENAI_API_KEY`"
    assert is_alarm is True


def test_describe_llm_status_ollama_unavailable() -> None:
    config = LLMConfig(provider="ollama", provider_explicit=True)

    with patch(_IS_OLLAMA_AVAILABLE, return_value=False):
        provider, message, is_alarm = describe_llm_status(config)

    assert provider is None
    assert message == "`ollama` configurado pero no responde"
    assert is_alarm is True


def test_describe_llm_status_available_and_explicit_has_no_message() -> None:
    config = LLMConfig(provider="ollama", provider_explicit=True)

    with patch(_IS_OLLAMA_AVAILABLE, return_value=True), patch(_OLLAMA_PROVIDER):
        provider, message, is_alarm = describe_llm_status(config)

    assert provider is not None
    assert message is None
    assert is_alarm is False


def test_describe_llm_status_default_fallback_available() -> None:
    """`LLM_PROVIDER` ausente pero el proveedor por defecto SÍ responde: mensaje
    informativo siempre presente (única combinación con mensaje pese a disponible), y
    la única que produce `is_alarm=False` con mensaje no vacío."""
    config = LLMConfig(provider="ollama", provider_explicit=False)

    with patch(_IS_OLLAMA_AVAILABLE, return_value=True), patch(_OLLAMA_PROVIDER):
        provider, message, is_alarm = describe_llm_status(config)

    assert provider is not None
    assert message == "`LLM_PROVIDER` no definida, usando `ollama` por defecto"
    assert is_alarm is False


def test_describe_llm_status_default_fallback_unavailable_combines_reason() -> None:
    """Mensaje combinado (default + inalcanzable): el texto combina ambos motivos, pero
    `is_alarm` es `True` — "warning gana" sobre el aviso informativo puro."""
    config = LLMConfig(provider="ollama", provider_explicit=False)

    with patch(_IS_OLLAMA_AVAILABLE, return_value=False):
        provider, message, is_alarm = describe_llm_status(config)

    assert provider is None
    assert message == (
        "`LLM_PROVIDER` no definida, usando `ollama` por defecto "
        "(`ollama` configurado pero no responde)"
    )
    assert is_alarm is True


def test_describe_llm_status_unrecognized_provider() -> None:
    """No es una de las 5 combinaciones de `design.md`, pero tampoco queda en silencio."""
    config = LLMConfig(provider="grok", provider_explicit=True)

    provider, message, is_alarm = describe_llm_status(config)

    assert provider is None
    assert message == (
        "`grok` no es un proveedor reconocido "
        "(valores válidos: ollama, deepseek, openai, disabled)"
    )
    assert is_alarm is True


def test_describe_llm_status_provider_matches_build_provider_for_same_config() -> None:
    config = LLMConfig(provider="deepseek", deepseek_api_key="sk-test")

    with patch(_OPENAI_COMPATIBLE_PROVIDER) as mock_provider:
        expected = build_provider(config)
        provider, _, _ = describe_llm_status(config)

    assert mock_provider.return_value is expected
    assert provider is expected
