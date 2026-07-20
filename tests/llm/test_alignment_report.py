"""Tests de `extraer_alineaciones_del_informe` (R7, tarea 7): mirror de
`test_filter_report.py` para la extracción de alineación estratégica."""
from __future__ import annotations

import json

from agente_ong.llm.alignment_report import extraer_alineaciones_del_informe
from agente_ong.llm.provider import LLMProvider, LLMResponse
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport

_JSON_VALIDO = json.dumps(
    {
        "ods": [3],
        "prioridades_geograficas": [],
        "enfoques_transversales": [],
        "sectores_plan_director": [],
    }
)


def _opportunity(title: str, *, url: str | None = None) -> GrantOpportunity:
    def claim(field_name: str, value: str | None = None) -> Claim:
        return Claim(field=field_name, value=value)

    return GrantOpportunity(
        title=claim("titulo", title),
        organism=claim("organismo", "Ministerio"),
        amount=claim("importe"),
        deadline=claim("plazo"),
        scope=claim("ambito"),
        url=claim("url", url or f"https://x.es/{title}"),
    )


class _SequenceLLMProvider(LLMProvider):
    """Doble local: una respuesta o fallo distinto por llamada, en secuencia."""

    def __init__(self, outcomes: list[str | BaseException]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return LLMResponse(text=outcome, input_tokens=0, output_tokens=0)


# --- Solo se extrae para veredicto "si" ---


def test_extrae_alineacion_solo_para_veredicto_si() -> None:
    relevante = _opportunity("relevante")
    descartada = _opportunity("descartada")
    no_clasificada_provider = _opportunity("no_clasificada_provider")
    no_clasificada_response = _opportunity("no_clasificada_response")
    report = ResearchReport(
        mode="calls",
        opportunities=[relevante, descartada, no_clasificada_provider, no_clasificada_response],
    )
    classifications = {
        id(relevante): "si",
        id(descartada): "no",
        id(no_clasificada_provider): "no_clasificado_provider",
        id(no_clasificada_response): "no_clasificado_response",
    }
    provider = _SequenceLLMProvider([_JSON_VALIDO])

    resultado = extraer_alineaciones_del_informe(provider, report, classifications)

    assert set(resultado.keys()) == {id(relevante)}
    assert resultado[id(relevante)].ods == [3]
    assert len(provider.calls) == 1  # solo una llamada, para la relevante


def test_opportunity_sin_entrada_en_classifications_no_se_procesa() -> None:
    huerfana = _opportunity("huerfana")
    report = ResearchReport(mode="calls", opportunities=[huerfana])
    provider = _SequenceLLMProvider([])

    resultado = extraer_alineaciones_del_informe(provider, report, classifications={})

    assert resultado == {}
    assert provider.calls == []


# --- Aislamiento de fallos: una convocatoria falla, las demás siguen ---


def test_fallo_de_extraccion_en_una_convocatoria_no_afecta_a_las_demas() -> None:
    ok = _opportunity("ok")
    falla = _opportunity("falla")
    tambien_ok = _opportunity("tambien_ok")
    report = ResearchReport(mode="calls", opportunities=[ok, falla, tambien_ok])
    classifications = {id(ok): "si", id(falla): "si", id(tambien_ok): "si"}
    provider = _SequenceLLMProvider([_JSON_VALIDO, "esto no es JSON", _JSON_VALIDO])

    resultado = extraer_alineaciones_del_informe(provider, report, classifications)

    assert set(resultado.keys()) == {id(ok), id(tambien_ok)}
    assert id(falla) not in resultado


# --- Informe vacío / modo training ---


def test_informe_vacio_devuelve_dict_vacio_sin_llamadas() -> None:
    report = ResearchReport(mode="training", opportunities=[])
    provider = _SequenceLLMProvider([])

    resultado = extraer_alineaciones_del_informe(provider, report, classifications={})

    assert resultado == {}
    assert provider.calls == []


# --- Texto enviado al extractor ---


def test_texto_enviado_incluye_titulo_y_organismo() -> None:
    opp = _opportunity("Convocatoria de ejemplo")
    report = ResearchReport(mode="calls", opportunities=[opp])
    provider = _SequenceLLMProvider([_JSON_VALIDO])

    extraer_alineaciones_del_informe(provider, report, classifications={id(opp): "si"})

    _, user_enviado = provider.calls[0]
    assert "Convocatoria de ejemplo" in user_enviado
    assert "Ministerio" in user_enviado
