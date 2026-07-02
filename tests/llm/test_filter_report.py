"""Tests de `classify_report` (T8): integración del filtro con `report.opportunities`,
aislamiento de fallos y no-op en modo "training" (opportunities=[])."""

from __future__ import annotations

import logging

import pytest

from agente_ong.llm.errors import LLMConnectionError
from agente_ong.llm.filter_report import classify_report
from agente_ong.llm.provider import LLMProvider, LLMResponse
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport, VerificationStatus
from llm.fakes import FakeLLMProvider


def _opportunity(
    title: str,
    *,
    url: str | None = None,
    organism: str | None = "Ministerio",
    result_type: str = "convocatoria_probable",
) -> GrantOpportunity:
    return GrantOpportunity(
        title=Claim(field="titulo", value=title, status=VerificationStatus.VERIFIED),
        organism=Claim(field="organismo", value=organism),
        amount=Claim(field="importe"),
        deadline=Claim(field="plazo"),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value=url or f"https://x.es/{title}"),
        overall_status=VerificationStatus.VERIFIED,
        result_type=result_type,
    )


class _SequenceLLMProvider(LLMProvider):
    """Proveedor de prueba LOCAL (no toca tests/llm/fakes.py): una respuesta o fallo
    distinto por llamada, en secuencia — `FakeLLMProvider` (T1) solo soporta una
    respuesta/fallo constante, insuficiente para simular resultados distintos por
    oportunidad dentro del mismo `classify_report`.
    """

    def __init__(self, outcomes: list[str | BaseException]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return LLMResponse(text=outcome, input_tokens=0, output_tokens=0)


def test_classify_report_maps_each_opportunity_id_to_its_classification() -> None:
    opportunities = [_opportunity("A"), _opportunity("B"), _opportunity("C")]
    report = ResearchReport(mode="calls", opportunities=opportunities)
    provider = _SequenceLLMProvider(["SI", "NO", "basura"])

    result = classify_report(provider, report)

    assert result[id(opportunities[0])] == "si"
    assert result[id(opportunities[1])] == "no"
    assert result[id(opportunities[2])] == "no_clasificado"
    assert len(result) == 3


def test_classify_report_empty_opportunities_returns_empty_dict_without_calling_provider() -> None:
    report = ResearchReport(mode="training", opportunities=[])
    fake = FakeLLMProvider(text="SI")

    result = classify_report(fake, report)

    assert result == {}
    assert fake.calls == []


def test_classify_report_isolates_failures_and_continues() -> None:
    opportunities = [_opportunity("Falla"), _opportunity("Responde")]
    report = ResearchReport(mode="calls", opportunities=opportunities)
    provider = _SequenceLLMProvider([LLMConnectionError("red caida"), "SI"])

    result = classify_report(provider, report)

    assert result[id(opportunities[0])] == "no_clasificado"
    assert result[id(opportunities[1])] == "si"
    assert len(result) == 2


def test_classify_report_does_not_mutate_result_type() -> None:
    opportunities = [
        _opportunity("A", result_type="convocatoria_probable"),
        _opportunity("B", result_type="documento_informativo"),
    ]
    report = ResearchReport(mode="calls", opportunities=opportunities)
    before = [opp.result_type for opp in opportunities]
    provider = _SequenceLLMProvider(["SI", "NO"])

    classify_report(provider, report)

    after = [opp.result_type for opp in opportunities]
    assert after == before


def test_classify_report_keys_are_object_identity_not_index_or_url() -> None:
    opportunities = [_opportunity("A", url="https://x.es/a"), _opportunity("B", url="https://x.es/b")]
    report = ResearchReport(mode="calls", opportunities=opportunities)
    provider = _SequenceLLMProvider(["SI", "NO"])

    result = classify_report(provider, report)

    assert set(result.keys()) == {id(opportunities[0]), id(opportunities[1])}
    assert 0 not in result and 1 not in result  # no son índices
    assert "https://x.es/a" not in result  # no son urls


def test_classify_report_logs_warning_on_llm_error(caplog: pytest.LogCaptureFixture) -> None:
    opportunities = [_opportunity("Falla")]
    report = ResearchReport(mode="calls", opportunities=opportunities)
    provider = _SequenceLLMProvider([LLMConnectionError("red caida")])

    with caplog.at_level(logging.WARNING, logger="agente_ong.llm.filter_report"):
        classify_report(provider, report)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert "LLMConnectionError" in record.getMessage()
