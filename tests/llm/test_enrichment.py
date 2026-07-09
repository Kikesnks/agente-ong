"""Tests de `EnrichedReport`/`enrich_report` (R7, T10).

`_SequencedProvider` es un doble LOCAL (no vive en `tests/llm/fakes.py`): a diferencia de
`FakeLLMProvider` (una única respuesta fija para todas las llamadas), estos tests necesitan
una respuesta o fallo DISTINTO por oportunidad, en el orden en que `classify_report`
recorre `report.opportunities` (T8, no se toca).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agente_ong.llm.enrichment import EnrichedReport, enrich_report
from agente_ong.llm.errors import LLMConnectionError
from agente_ong.llm.provider import LLMProvider, LLMResponse
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport


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
    assert enriched.discarded == []
    assert enriched.unclassified == []
    assert enriched.semantic_filter_applied is False


# --- Con provider: 3 buckets (R7.2/R7.4) ---


def test_enrich_report_with_provider_separates_into_three_buckets() -> None:
    kept_opp = _opportunity("kept")
    discarded_opp = _opportunity("discarded")
    unclassified_opp = _opportunity("unclassified")
    report = _report(kept_opp, discarded_opp, unclassified_opp)
    provider = _SequencedProvider(responses=["SI", "NO", "esto no es SI ni NO"])

    enriched = enrich_report(report, provider)

    assert enriched.base.opportunities == [kept_opp]
    assert enriched.discarded == [discarded_opp]
    assert enriched.unclassified == [unclassified_opp]
    assert enriched.semantic_filter_applied is True
    # El report ORIGINAL no se muta (R7.2): sigue con las 3 oportunidades.
    assert report.opportunities == [kept_opp, discarded_opp, unclassified_opp]


# --- Fallo de clasificación aislado (R7.5) ---


def test_enrich_report_llm_error_on_one_opportunity_goes_to_unclassified() -> None:
    first = _opportunity("first")
    failing = _opportunity("failing")
    third = _opportunity("third")
    report = _report(first, failing, third)
    provider = _SequencedProvider(
        responses=["SI", LLMConnectionError("fallo simulado"), "SI"]
    )

    enriched = enrich_report(report, provider)

    assert enriched.base.opportunities == [first, third]
    assert enriched.discarded == []
    assert enriched.unclassified == [failing]
    assert enriched.semantic_filter_applied is True


# --- Aristas: informe vacío ---


def test_enrich_report_without_provider_and_empty_opportunities() -> None:
    report = _report()

    enriched = enrich_report(report, None)

    assert enriched.base is report
    assert enriched.discarded == []
    assert enriched.unclassified == []
    assert enriched.semantic_filter_applied is False


def test_enrich_report_with_provider_and_empty_opportunities_is_noop() -> None:
    """Modo "training": report.opportunities es [] por diseño (R23.3 de investigador-v2);
    con provider disponible, el filtro no tiene nada que clasificar."""
    report = _report()
    provider = _SequencedProvider(responses=[])

    enriched = enrich_report(report, provider)

    assert enriched.base.opportunities == []
    assert enriched.discarded == []
    assert enriched.unclassified == []
    assert enriched.semantic_filter_applied is True
    assert provider.calls == 0


def test_enrich_report_does_not_mutate_original_report_object() -> None:
    """`report` de entrada debe seguir siendo un objeto DISTINTO de `enriched.base` en
    cuanto hay provider (dataclasses.replace crea uno nuevo), aunque comparen igual en
    campos no tocados."""
    report = _report(_opportunity("a"))
    provider = _SequencedProvider(responses=["SI"])

    enriched = enrich_report(report, provider)

    assert enriched.base is not report
    assert enriched.base.ledger == report.ledger
    assert enriched.base.failed_sources == report.failed_sources
    assert enriched.base.mode == report.mode
