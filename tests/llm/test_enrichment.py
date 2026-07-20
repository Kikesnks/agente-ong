"""Tests de `EnrichedReport`/`enrich_report` (R7 de `integracion-llm`, T10; T3 de
`descartados-filtro`; R7 de `alineacion-estrategica`, tarea 7).

`_SequencedProvider` es un doble LOCAL (no vive en `tests/llm/fakes.py`): a diferencia de
`FakeLLMProvider` (una única respuesta fija para todas las llamadas), estos tests necesitan
una respuesta o fallo DISTINTO por llamada, en el orden en que `enrich_report` llama al
proveedor: primero `classify_report` recorre `report.opportunities` para clasificar (T8,
no se toca), después `extraer_alineaciones_del_informe` recorre las MISMAS oportunidades
en el mismo orden, pero solo llama al proveedor para las de veredicto "si" (tarea 7).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import pytest

from agente_ong.llm.enrichment import EnrichedReport, enrich_report
from agente_ong.llm.errors import LLMConnectionError
from agente_ong.llm.provider import LLMProvider, LLMResponse
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport

# JSON mínimo válido de alineación (las cuatro listas vacías): basta para que
# `parsear_alineacion` (tarea 4) lo acepte sin lanzar `AlignmentParseError`; el contenido
# no importa a estos tests de cableado, solo que la extracción "tenga éxito".
_JSON_ALINEACION_VALIDA = json.dumps(
    {
        "ods": [],
        "prioridades_geograficas": [],
        "enfoques_transversales": [],
        "sectores_plan_director": [],
    }
)


@dataclass
class _SequencedProvider(LLMProvider):
    """Doble local: una respuesta (texto) o excepción distinta por llamada, en orden."""

    responses: list[str | BaseException]
    calls: int = field(default=0, init=False)

    def complete(self, system: str, user: str) -> LLMResponse:
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        return LLMResponse(text=item, input_tokens=0, output_tokens=0)


def _opportunity(title_value: str) -> GrantOpportunity:
    def claim(field_name: str, value: str | None = None) -> Claim:
        return Claim(field=field_name, value=value)

    return GrantOpportunity(
        title=claim("titulo", title_value),
        organism=claim("organismo"),
        amount=claim("importe"),
        deadline=claim("plazo"),
        scope=claim("ambito"),
        url=claim("url", f"https://example.org/{title_value}"),
    )


def _report(*opportunities: GrantOpportunity) -> ResearchReport:
    return ResearchReport(mode="calls", opportunities=list(opportunities))


# --- Sin provider: degradación silenciosa (R7.3) ---


def test_enrich_report_without_provider_returns_report_untouched() -> None:
    report = _report(_opportunity("a"), _opportunity("b"), _opportunity("c"))

    enriched = enrich_report(report, None)

    assert isinstance(enriched, EnrichedReport)
    assert enriched.base is report  # misma referencia, no clon
    assert enriched.base.filter_verdicts == {}
    assert enriched.semantic_filter_applied is False
    assert enriched.strategic_alignment == {}


# --- Con provider: nada se filtra, todo se conserva en filter_verdicts (T3) ---


def test_enrich_report_with_provider_keeps_all_opportunities_and_fills_verdicts() -> None:
    kept_opp = _opportunity("kept")
    discarded_opp = _opportunity("discarded")
    unclassified_opp = _opportunity("unclassified")
    report = _report(kept_opp, discarded_opp, unclassified_opp)
    # 3 respuestas de clasificación + 1 de alineación (solo "kept" tiene veredicto "si").
    provider = _SequencedProvider(
        responses=["SI", "NO", "esto no es SI ni NO", _JSON_ALINEACION_VALIDA]
    )

    enriched = enrich_report(report, provider)

    # base.opportunities queda IDÉNTICA a report.opportunities: nada se filtra.
    assert enriched.base.opportunities == [kept_opp, discarded_opp, unclassified_opp]
    assert enriched.base.filter_verdicts == {
        "https://example.org/kept": "si",
        "https://example.org/discarded": "no",
        "https://example.org/unclassified": "no_clasificado_response",
    }
    assert enriched.semantic_filter_applied is True
    # El report ORIGINAL no se muta (R7.2): sigue con las 3 oportunidades y sin veredictos.
    assert report.opportunities == [kept_opp, discarded_opp, unclassified_opp]
    assert report.filter_verdicts == {}
    # Solo la convocatoria relevante ("si") tiene alineación extraída (tarea 7).
    assert set(enriched.strategic_alignment.keys()) == {"https://example.org/kept"}


# --- Fallo de clasificación aislado (R7.5) ---


def test_enrich_report_llm_error_on_one_opportunity_records_provider_verdict() -> None:
    first = _opportunity("first")
    failing = _opportunity("failing")
    third = _opportunity("third")
    report = _report(first, failing, third)
    # 3 respuestas de clasificación + 2 de alineación ("first" y "third" son "si").
    provider = _SequencedProvider(
        responses=[
            "SI",
            LLMConnectionError("fallo simulado"),
            "SI",
            _JSON_ALINEACION_VALIDA,
            _JSON_ALINEACION_VALIDA,
        ]
    )

    enriched = enrich_report(report, provider)

    assert enriched.base.opportunities == [first, failing, third]
    assert enriched.base.filter_verdicts == {
        "https://example.org/first": "si",
        "https://example.org/failing": "no_clasificado_provider",
        "https://example.org/third": "si",
    }
    assert enriched.semantic_filter_applied is True
    assert set(enriched.strategic_alignment.keys()) == {
        "https://example.org/first",
        "https://example.org/third",
    }


# --- Aristas: informe vacío ---


def test_enrich_report_without_provider_and_empty_opportunities() -> None:
    report = _report()

    enriched = enrich_report(report, None)

    assert enriched.base is report
    assert enriched.base.filter_verdicts == {}
    assert enriched.semantic_filter_applied is False


def test_enrich_report_with_provider_and_empty_opportunities_is_noop() -> None:
    """Modo "training": report.opportunities es [] por diseño (R23.3 de investigador-v2);
    con provider disponible, el filtro no tiene nada que clasificar."""
    report = _report()
    provider = _SequencedProvider(responses=[])

    enriched = enrich_report(report, provider)

    assert enriched.base.opportunities == []
    assert enriched.base.filter_verdicts == {}
    assert enriched.semantic_filter_applied is True
    assert provider.calls == 0


def test_enrich_report_does_not_mutate_original_report_object() -> None:
    """`report` de entrada debe seguir siendo un objeto DISTINTO de `enriched.base` en
    cuanto hay provider (dataclasses.replace crea uno nuevo), aunque comparen igual en
    campos no tocados."""
    report = _report(_opportunity("a"))
    provider = _SequencedProvider(responses=["SI", _JSON_ALINEACION_VALIDA])

    enriched = enrich_report(report, provider)

    assert enriched.base is not report
    assert enriched.base.ledger == report.ledger
    assert enriched.base.failed_sources == report.failed_sources
    assert enriched.base.mode == report.mode


# --- Extracción de alineación estratégica (R7 de `alineacion-estrategica`, tarea 7) ---


def test_enrich_report_extracts_alignment_only_for_relevant_opportunity() -> None:
    kept_opp = _opportunity("kept")
    discarded_opp = _opportunity("discarded")
    report = _report(kept_opp, discarded_opp)
    provider = _SequencedProvider(responses=["SI", "NO", _JSON_ALINEACION_VALIDA])

    enriched = enrich_report(report, provider)

    assert enriched.strategic_alignment.keys() == {"https://example.org/kept"}
    assert enriched.strategic_alignment["https://example.org/kept"].ods == []
    # La descartada no dispara ninguna llamada de extracción: 2 clasificación + 1 alineación.
    assert provider.calls == 3


def test_enrich_report_alignment_failure_on_one_opportunity_does_not_affect_others() -> None:
    """Fallo puntual de extracción (respuesta malformada) en una convocatoria relevante:
    esa URL queda ausente de `strategic_alignment`, las demás se procesan igual (R7.5)."""
    ok_opp = _opportunity("ok")
    broken_opp = _opportunity("broken")
    report = _report(ok_opp, broken_opp)
    provider = _SequencedProvider(
        responses=[
            "SI",  # clasificación de ok_opp
            "SI",  # clasificación de broken_opp
            _JSON_ALINEACION_VALIDA,  # alineación de ok_opp
            "esto no es JSON",  # alineación de broken_opp: falla el parseo
        ]
    )

    enriched = enrich_report(report, provider)

    assert enriched.strategic_alignment.keys() == {"https://example.org/ok"}
    assert "https://example.org/broken" not in enriched.strategic_alignment


def test_enrich_report_alignment_failure_logs_error(caplog: pytest.LogCaptureFixture) -> None:
    broken_opp = _opportunity("broken")
    report = _report(broken_opp)
    provider = _SequencedProvider(responses=["SI", "esto no es JSON"])

    with caplog.at_level(logging.ERROR, logger="agente_ong.llm.alignment_extractor"):
        enrich_report(report, provider)

    assert any(r.levelno == logging.ERROR for r in caplog.records)
