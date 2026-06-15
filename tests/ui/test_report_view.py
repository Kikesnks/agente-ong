"""Tests del orden y los filtros de convocatorias (`ui/report_view.py`).

Orden canónico por estado de verificación, filtros por estado/año/importe, combinación AND
que mantiene el orden, y manejo explícito de `Claim.value is None` (nunca como cero).
_Requirements: 11.1, 11.2, 11.3, 11.4_
"""

from __future__ import annotations

from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport, VerificationStatus
from agente_ong.ui.report_serde import opportunity_numbers
from agente_ong.ui.report_view import (
    STATUS_ORDER,
    filter_opportunities,
    partition_by_actionability,
    sort_opportunities,
)


def _opp(
    title: str,
    status: VerificationStatus,
    *,
    deadline: str | None = None,
    amount: str | None = None,
    result_type: str = "desconocido",
) -> GrantOpportunity:
    return GrantOpportunity(
        title=Claim(field="titulo", value=title, status=status),
        organism=Claim(field="organismo"),
        amount=Claim(field="importe", value=amount, is_critical=True),
        deadline=Claim(field="plazo", value=deadline, is_critical=True),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value=f"https://x.es/{title}"),
        overall_status=status,
        result_type=result_type,
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


# --- Partición por accionabilidad (R20.2) ---


def test_partition_separates_informational_from_actionable() -> None:
    a = _opp("conv", VerificationStatus.OFFICIAL_UNCROSSED, result_type="convocatoria_probable")
    b = _opp("desc", VerificationStatus.NOT_FOUND, result_type="desconocido")
    c = _opp("info", VerificationStatus.UNCROSSED_UNVERIFIED, result_type="documento_informativo")

    actionable, informational = partition_by_actionability([a, b, c])
    assert _titles(actionable) == ["conv", "desc"]  # probable + desconocido
    assert _titles(informational) == ["info"]


def test_partition_preserves_order() -> None:
    opps = [
        _opp("i1", VerificationStatus.VERIFIED, result_type="documento_informativo"),
        _opp("a1", VerificationStatus.VERIFIED, result_type="convocatoria_probable"),
        _opp("i2", VerificationStatus.VERIFIED, result_type="documento_informativo"),
    ]
    actionable, informational = partition_by_actionability(opps)
    assert _titles(actionable) == ["a1"]
    assert _titles(informational) == ["i1", "i2"]


# --- R14.3: número estable con sort + filter ---


def test_opportunity_number_stable_after_sort_and_filter() -> None:
    """R14.3: el número de una convocatoria no cambia si sort/filter la mueven o la ocultan.

    Verifica también el supuesto de id(): sort_opportunities y filter_opportunities devuelven
    referencias a los mismos objetos (no copias). Si devolvieran copias, id() no casaría y
    el dict daría KeyError o el número incorrecto.
    """
    opp_first = _opp("first", VerificationStatus.VERIFIED, result_type="convocatoria_probable")
    opp_second = _opp("second", VerificationStatus.NOT_FOUND, result_type="convocatoria_probable")
    report = ResearchReport(mode="calls", opportunities=[opp_first, opp_second])

    numbers = opportunity_numbers(report)
    assert numbers[id(opp_first)] == 1
    assert numbers[id(opp_second)] == 2

    # Flujo de render_report: sort → partition → filter que oculta opp_first.
    sorted_opps = sort_opportunities(report.opportunities)
    actionable, _ = partition_by_actionability(sorted_opps)
    filtered = filter_opportunities(actionable, status=VerificationStatus.NOT_FOUND)

    # Solo opp_second pasa el filtro; debe conservar su número original (2, no 1).
    assert filtered == [opp_second]  # misma referencia, no copia
    assert numbers[id(filtered[0])] == 2
