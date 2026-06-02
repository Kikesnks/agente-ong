"""Tests de `VerificationPolicy` (veracidad, verificación cruzada y revalidación).

Cubre la tabla de `classify` (incluida la distinción OFFICIAL_UNCROSSED vs
UNCROSSED_UNVERIFIED) y los casos de `needs_revalidation` (crítico+propuesta, caducidad,
pista de ledger no reconfirmada). _Requirements: 3.3, 3.4, 4.2, 4.4_
"""

from datetime import datetime, timedelta, timezone

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import Claim, SourceRef, VerificationStatus
from agente_ong.research.verification import VerificationPolicy

NOW = datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.fixture
def policy() -> VerificationPolicy:
    return VerificationPolicy(ResearchConfig(staleness_days=30))


def _src(*, official: bool = False, days_ago: int = 0) -> SourceRef:
    return SourceRef(
        url="https://x.es/a",
        source_name="bdns" if official else "tavily",
        is_official=official,
        retrieved_at=NOW - timedelta(days=days_ago),
    )


def _claim(value: str | None = "50000", *, critical: bool = True, sources=None) -> Claim:
    return Claim(field="importe", value=value, is_critical=critical, sources=sources or [])


# --- classify ---


def test_classify_no_value_is_not_found(policy: VerificationPolicy) -> None:
    assert policy.classify(_claim(None), []) is VerificationStatus.NOT_FOUND


def test_classify_no_sources_is_not_found(policy: VerificationPolicy) -> None:
    assert policy.classify(_claim("x"), []) is VerificationStatus.NOT_FOUND


@pytest.mark.parametrize(
    "supporting",
    [
        [_src(), _src()],  # dos no oficiales
        [_src(official=True), _src()],  # oficial + no oficial
    ],
)
def test_classify_two_or_more_is_verified(policy: VerificationPolicy, supporting) -> None:
    assert policy.classify(_claim(), supporting) is VerificationStatus.VERIFIED


def test_classify_single_official_is_official_uncrossed(policy: VerificationPolicy) -> None:
    assert policy.classify(_claim(), [_src(official=True)]) is VerificationStatus.OFFICIAL_UNCROSSED


def test_classify_single_non_official_is_uncrossed_unverified(policy: VerificationPolicy) -> None:
    assert (
        policy.classify(_claim(), [_src(official=False)])
        is VerificationStatus.UNCROSSED_UNVERIFIED
    )


@pytest.mark.parametrize(
    "supporting",
    [
        [_src(official=True), _src()],  # con respaldo verificado
        [_src(official=True)],  # con respaldo oficial
    ],
)
def test_classify_conflicting_takes_precedence(policy: VerificationPolicy, supporting) -> None:
    # Una contradicción siempre se señala, por encima de cualquier respaldo.
    result = policy.classify(_claim(), supporting, conflicting=[_src()])
    assert result is VerificationStatus.CONFLICTING


# --- needs_revalidation ---


def test_revalidation_critical_for_proposal(policy: VerificationPolicy) -> None:
    # Crítico + se va a usar en propuesta => revalidar (aunque la fuente sea fresca).
    claim = _claim(critical=True, sources=[_src(days_ago=1)])
    assert policy.needs_revalidation(claim, intent="use_in_proposal", now=NOW) is True


def test_no_revalidation_when_fresh_and_exploring(policy: VerificationPolicy) -> None:
    claim = _claim(critical=True, sources=[_src(days_ago=1)])
    assert policy.needs_revalidation(claim, intent="explore", now=NOW) is False
    assert claim.stale is False


def test_revalidation_when_stale_marks_stale(policy: VerificationPolicy) -> None:
    # No crítico, explorando, pero fuente caducada => revalidar y marcar stale.
    claim = _claim(critical=False, sources=[_src(days_ago=40), _src(days_ago=100)])
    assert policy.needs_revalidation(claim, intent="explore", now=NOW) is True
    assert claim.stale is True


@pytest.mark.parametrize(
    "days_ago, expected_stale",
    [(30, False), (31, True)],  # umbral estricto: 30 no caduca, 31 sí
)
def test_staleness_threshold_is_strict(
    policy: VerificationPolicy, days_ago: int, expected_stale: bool
) -> None:
    claim = _claim(critical=False, sources=[_src(days_ago=days_ago)])
    assert policy.needs_revalidation(claim, intent="explore", now=NOW) is expected_stale
    assert claim.stale is expected_stale


def test_revalidation_critical_from_ledger_only(policy: VerificationPolicy) -> None:
    # Crítico que solo proviene de una pista de ledger no reconfirmada => revalidar.
    claim = _claim(critical=True, sources=[])
    assert (
        policy.needs_revalidation(claim, intent="explore", now=NOW, from_ledger_only=True) is True
    )


def test_no_revalidation_non_critical_from_ledger_only(policy: VerificationPolicy) -> None:
    claim = _claim(critical=False, sources=[])
    assert (
        policy.needs_revalidation(claim, intent="explore", now=NOW, from_ledger_only=True) is False
    )


def test_no_sources_means_not_stale(policy: VerificationPolicy) -> None:
    claim = _claim(critical=False, sources=[])
    assert policy.needs_revalidation(claim, intent="explore", now=NOW) is False
    assert claim.stale is False
