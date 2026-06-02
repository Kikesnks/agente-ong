"""Tests de `DepthLimiter` (corte por profundidad, páginas y consultas).

_Requirements: 6.3, NFR Performance_
"""

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.depth import DepthLimiter


@pytest.fixture
def limiter() -> DepthLimiter:
    # Límites pequeños y distintos para distinguir qué tope corta en cada caso.
    return DepthLimiter(ResearchConfig(max_depth=3, max_pages=10, max_queries=5))


def test_can_expand_when_under_all_limits(limiter: DepthLimiter) -> None:
    assert limiter.can_expand(current_depth=0, pages_fetched=0, queries_made=0) is True
    assert limiter.can_expand(current_depth=2, pages_fetched=9, queries_made=4) is True


def test_blocks_when_depth_reached(limiter: DepthLimiter) -> None:
    assert limiter.can_expand(current_depth=3, pages_fetched=0, queries_made=0) is False
    assert limiter.can_expand(current_depth=4, pages_fetched=0, queries_made=0) is False


def test_blocks_when_pages_reached(limiter: DepthLimiter) -> None:
    assert limiter.can_expand(current_depth=0, pages_fetched=10, queries_made=0) is False
    assert limiter.can_expand(current_depth=0, pages_fetched=11, queries_made=0) is False


def test_blocks_when_queries_reached(limiter: DepthLimiter) -> None:
    assert limiter.can_expand(current_depth=0, pages_fetched=0, queries_made=5) is False
    assert limiter.can_expand(current_depth=0, pages_fetched=0, queries_made=6) is False


def test_any_single_limit_blocks(limiter: DepthLimiter) -> None:
    # Aunque dos límites tengan margen, basta con que uno se alcance para cortar.
    assert limiter.can_expand(current_depth=2, pages_fetched=9, queries_made=5) is False


def test_queries_made_defaults_to_zero(limiter: DepthLimiter) -> None:
    # La firma del diseño (dos args) sigue siendo válida: queries_made por defecto 0.
    assert limiter.can_expand(current_depth=1, pages_fetched=1) is True


def test_uses_config_defaults() -> None:
    # Con la config por defecto (depth=3, pages=50, queries=30).
    limiter = DepthLimiter()
    assert limiter.can_expand(current_depth=2, pages_fetched=49, queries_made=29) is True
    assert limiter.can_expand(current_depth=3, pages_fetched=0, queries_made=0) is False
