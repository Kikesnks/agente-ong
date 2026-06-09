"""Tests del orden y los filtros de convocatorias (`ui/report_view.py`).

Orden canónico por estado de verificación, filtros por estado/año/importe, combinación AND
que mantiene el orden, y manejo explícito de `Claim.value is None` (nunca como cero).
_Requirements: 11.1, 11.2, 11.3, 11.4_
"""

from __future__ import annotations

from agente_ong.research.models import Claim, GrantOpportunity, VerificationStatus
from agente_ong.ui.report_view import STATUS_ORDER, filter_opportunities, sort_opportunities


def _opp(
    title: str,
    status: VerificationStatus,
    *,
    deadline: str | None = None,
    amount: str | None = None,
) -> GrantOpportunity:
    return GrantOpportunity(
        title=Claim(field="titulo", value=title, status=status),
        organism=Claim(field="organismo"),
        amount=Claim(field="importe", value=amount, is_critical=True),
        deadline=Claim(field="plazo", value=deadline, is_critical=True),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value=f"https://x.es/{title}"),
        overall_status=status,
    )


def _titles(opps: list[GrantOpportunity]) -> list[str]:
    return [o.title.value for o in opps]


# --- Orden canónico (R11.1) ---


def test_sort_follows_canonical_status_order() -> None:
    # Entrada deliberadamente en orden inverso al canónico.
    opps = [
        _opp("nf", VerificationStatus.NOT_FOUND),
        _opp("conf", VerificationStatus.CONFLICTING),
        _opp("uncrossed", VerificationStatus.UNCROSSED_UNVERIFIED),
        _opp("official", VerificationStatus.OFFICIAL_UNCROSSED),
        _opp("verified", VerificationStatus.VERIFIED),
    ]
    assert _titles(sort_opportunities(opps)) == [
        "verified",
        "official",
        "uncrossed",
        "conf",
        "nf",
    ]
    # El orden canónico publicado cubre los 5 estados, de más a menos fiable.
    assert STATUS_ORDER[0] is VerificationStatus.VERIFIED
    assert STATUS_ORDER[-1] is VerificationStatus.NOT_FOUND
    assert len(STATUS_ORDER) == len(VerificationStatus)


def test_sort_is_stable_within_same_status() -> None:
    opps = [
        _opp("a", VerificationStatus.VERIFIED),
        _opp("nf", VerificationStatus.NOT_FOUND),
        _opp("b", VerificationStatus.VERIFIED),
    ]
    assert _titles(sort_opportunities(opps)) == ["a", "b", "nf"]


# --- Filtros individuales (R11.2, R11.3) ---


def test_filter_by_status() -> None:
    opps = [
        _opp("v", VerificationStatus.VERIFIED),
        _opp("o", VerificationStatus.OFFICIAL_UNCROSSED),
    ]
    assert _titles(filter_opportunities(opps, status=VerificationStatus.VERIFIED)) == ["v"]


def test_filter_by_min_year_uses_deadline_and_excludes_unknown() -> None:
    opps = [
        _opp("vieja", VerificationStatus.VERIFIED, deadline="31/12/2024"),
        _opp("vigente", VerificationStatus.VERIFIED, deadline="hasta el 15/03/2026"),
        _opp("sin plazo", VerificationStatus.VERIFIED, deadline=None),
        _opp("plazo raro", VerificationStatus.VERIFIED, deadline="abierta todo el año"),
    ]
    filtered = _titles(filter_opportunities(opps, min_year=2025))
    # Sin dato (None) o no parseable: excluida, nunca interpretada como año 0 (R11.3).
    assert filtered == ["vigente"]


def test_filter_by_min_amount_parses_values_and_excludes_none() -> None:
    opps = [
        _opp("grande", VerificationStatus.VERIFIED, amount="120.000 €"),
        _opp("pequeña", VerificationStatus.VERIFIED, amount="5.000 €"),
        _opp("sin importe", VerificationStatus.VERIFIED, amount=None),
    ]
    filtered = _titles(filter_opportunities(opps, min_amount=50_000))
    # value None excluida: no se cuela como cero (R11.3).
    assert filtered == ["grande"]


def test_no_filters_returns_everything_unchanged() -> None:
    opps = [_opp("a", VerificationStatus.VERIFIED), _opp("b", VerificationStatus.NOT_FOUND)]
    assert filter_opportunities(opps) == opps


# --- Combinación AND y conservación del orden (R11.4) ---


def test_combined_filters_are_anded_and_preserve_sorted_order() -> None:
    opps = sort_opportunities(
        [
            _opp("nf-2026", VerificationStatus.NOT_FOUND, deadline="2026", amount="90.000 €"),
            _opp("v-2026-grande", VerificationStatus.VERIFIED, deadline="2026", amount="100.000 €"),
            _opp("v-2024-grande", VerificationStatus.VERIFIED, deadline="2024", amount="100.000 €"),
            _opp("o-2026-grande", VerificationStatus.OFFICIAL_UNCROSSED, deadline="2026", amount="80.000 €"),
            _opp("v-2026-pequeña", VerificationStatus.VERIFIED, deadline="2026", amount="1.000 €"),
        ]
    )
    filtered = filter_opportunities(opps, min_year=2025, min_amount=50_000)
    # AND de criterios; el orden canónico (VERIFIED antes que OFFICIAL_UNCROSSED y NOT_FOUND)
    # se mantiene en el resultado.
    assert _titles(filtered) == ["v-2026-grande", "o-2026-grande", "nf-2026"]


def test_combined_with_status_filter() -> None:
    opps = [
        _opp("v-ok", VerificationStatus.VERIFIED, deadline="2026", amount="100.000 €"),
        _opp("o-ok", VerificationStatus.OFFICIAL_UNCROSSED, deadline="2026", amount="100.000 €"),
    ]
    filtered = filter_opportunities(
        opps, status=VerificationStatus.VERIFIED, min_year=2025, min_amount=50_000
    )
    assert _titles(filtered) == ["v-ok"]
