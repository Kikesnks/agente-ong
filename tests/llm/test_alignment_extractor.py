"""Tests de R7: extractor LLM de alineación estratégica (`extraer_alineacion`)."""
from __future__ import annotations

import json
import logging

import pytest

from agente_ong.llm.alignment_extractor import extraer_alineacion
from agente_ong.llm.errors import LLMConnectionError
from llm.fakes import FakeLLMProvider

_JSON_VALIDO = json.dumps(
    {
        "ods": [3, 5],
        "prioridades_geograficas": ["América Latina y el Caribe"],
        "enfoques_transversales": ["Enfoque de derechos humanos"],
        "sectores_plan_director": ["Gobernabilidad democrática"],
    }
)


# --- Caso 1: Ollama disponible + respuesta válida ---


def test_ollama_disponible_respuesta_valida_devuelve_alineacion_correcta() -> None:
    provider = FakeLLMProvider(text=_JSON_VALIDO)

    resultado = extraer_alineacion("texto de la convocatoria", provider)

    assert resultado is not None
    assert resultado.ods == [3, 5]
    assert resultado.prioridades_geograficas == ["América Latina y el Caribe"]
    assert resultado.enfoques_transversales == ["Enfoque de derechos humanos"]
    assert resultado.sectores_plan_director == ["Gobernabilidad democrática"]


# --- Caso 2: Ollama no disponible ---


def test_provider_none_devuelve_none_y_loggea_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="agente_ong.llm.alignment_extractor"):
        resultado = extraer_alineacion("texto de la convocatoria", None)

    assert resultado is None
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "no disponible" in caplog.records[0].getMessage()


# --- Caso 3: Ollama disponible + respuesta malformada ---


def test_respuesta_malformada_devuelve_none_y_loggea_error(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeLLMProvider(text="esto no es json")

    with caplog.at_level(logging.ERROR, logger="agente_ong.llm.alignment_extractor"):
        resultado = extraer_alineacion("texto de la convocatoria", provider)

    assert resultado is None
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR


# --- Caso 4: la llamada LLM lanza excepción ---


def test_fallo_en_la_llamada_llm_devuelve_none_y_loggea_error(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeLLMProvider(fail=LLMConnectionError("red caída"))

    with caplog.at_level(logging.ERROR, logger="agente_ong.llm.alignment_extractor"):
        resultado = extraer_alineacion("texto de la convocatoria", provider)

    assert resultado is None
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    assert "LLMConnectionError" in caplog.records[0].getMessage()


# --- Detalle: taxonomía inyectada en el prompt enviado ---


def test_system_prompt_enviado_tiene_la_taxonomia_sustituida_sin_marcadores() -> None:
    provider = FakeLLMProvider(text=_JSON_VALIDO)

    extraer_alineacion("texto de la convocatoria", provider)

    assert len(provider.calls) == 1
    system_enviado, user_enviado = provider.calls[0]
    assert "<<ODS>>" not in system_enviado
    assert "<<PRIORIDADES_GEOGRAFICAS>>" not in system_enviado
    assert "<<ENFOQUES_TRANSVERSALES>>" not in system_enviado
    assert "<<SECTORES_PLAN_DIRECTOR>>" not in system_enviado
    assert "Fin de la pobreza" in system_enviado  # ODS 1
    assert "América Latina y el Caribe" in system_enviado
    assert "Enfoque de derechos humanos" in system_enviado
    assert "Gobernabilidad democrática" in system_enviado
    assert user_enviado == "texto de la convocatoria"


# --- Detalle: opportunity_id se incluye en el log cuando se pasa ---


def test_opportunity_id_se_incluye_en_el_log_de_error(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeLLMProvider(fail=LLMConnectionError("red caída"))

    with caplog.at_level(logging.ERROR, logger="agente_ong.llm.alignment_extractor"):
        extraer_alineacion("texto", provider, opportunity_id="conv-42")

    assert "conv-42" in caplog.records[0].getMessage()


def test_opportunity_id_se_incluye_en_el_log_de_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="agente_ong.llm.alignment_extractor"):
        extraer_alineacion("texto", None, opportunity_id="conv-99")

    assert "conv-99" in caplog.records[0].getMessage()
