"""Tests del mapeo de controles de UI a config+request (`ui/request_builder.py`).

Presets de profundidad → (max_depth, max_pages), default "normal", propagación de min_year
(a la config, sin mutar la base), enabled_sources/direct_urls/search_context (al request) y
rechazo de la combinación sin fuentes ni URLs. _Requirements: 8.2, 8.3, 9.2, 10.1_
"""

from __future__ import annotations

import pytest

from agente_ong.research.config import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, ResearchConfig
from agente_ong.research.models import Scope
from agente_ong.ui.request_builder import DEFAULT_DEPTH_LEVEL, DEPTH_PRESETS, build


# --- Presets de profundidad (R8) ---


def test_presets_are_the_three_levels_with_increasing_values() -> None:
    assert set(DEPTH_PRESETS) == {"rápida", "normal", "exhaustiva"}
    depths = [DEPTH_PRESETS[k][0] for k in ("rápida", "normal", "exhaustiva")]
    pages = [DEPTH_PRESETS[k][1] for k in ("rápida", "normal", "exhaustiva")]
    assert depths == sorted(depths) and len(set(depths)) == 3  # crecientes (R8.2)
    assert pages == sorted(pages) and len(set(pages)) == 3


def test_normal_preset_matches_module_defaults() -> None:
    # "normal" = comportamiento por defecto del investigador, sin recorte ni esfuerzo extra.
    assert DEPTH_PRESETS["normal"] == (DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES)


@pytest.mark.parametrize("level", ["rápida", "normal", "exhaustiva"])
def test_build_maps_level_to_request_overrides(level: str) -> None:
    _, request = build(ResearchConfig(), terms=["cultura"], depth_level=level)
    assert (request.max_depth, request.max_pages) == DEPTH_PRESETS[level]


def test_build_defaults_to_normal_level() -> None:
    assert DEFAULT_DEPTH_LEVEL == "normal"  # R8.3
    _, request = build(ResearchConfig(), terms=["cultura"])
    assert (request.max_depth, request.max_pages) == DEPTH_PRESETS["normal"]


def test_build_rejects_unknown_level() -> None:
    with pytest.raises(ValueError):
        build(ResearchConfig(), terms=["x"], depth_level="turbo")


# --- Propagación de controles (R9/R10) ---


def test_min_year_goes_to_config_copy_without_mutating_base() -> None:
    base = ResearchConfig()
    config, _ = build(base, terms=["x"], min_year=2025)
    assert config.min_year == 2025
    assert base.min_year is None  # la config base no se muta
    # El resto de la config se preserva (misma db, mismos límites).
    assert config.db_path == base.db_path and config.max_queries == base.max_queries


def test_sources_urls_context_and_scope_go_to_request() -> None:
    scope = Scope(country="ES", eu=True)
    _, request = build(
        ResearchConfig(),
        terms=["cultura", "salud mental"],
        scope=scope,
        enabled_sources={"bdns", "tavily"},
        direct_urls=["https://ong.example/conv"],
        search_context="convocatoria subvención ONG",
    )
    assert request.mode == "calls"
    assert request.query_terms == ["cultura", "salud mental"]
    assert request.scope == scope
    assert request.enabled_sources == {"bdns", "tavily"}
    assert request.direct_urls == ["https://ong.example/conv"]
    assert request.search_context == "convocatoria subvención ONG"


def test_enabled_sources_none_means_all_sources() -> None:
    _, request = build(ResearchConfig(), terms=["x"])
    assert request.enabled_sources is None
    assert request.direct_urls == []


# --- Validación R9.5: sin fuentes ni URLs no hay investigación ---


def test_no_sources_and_no_urls_is_rejected() -> None:
    with pytest.raises(ValueError):
        build(ResearchConfig(), terms=["x"], enabled_sources=set())


def test_no_sources_but_direct_url_is_allowed() -> None:
    _, request = build(
        ResearchConfig(), terms=["x"], enabled_sources=set(), direct_urls=["https://u"]
    )
    assert request.enabled_sources == set()
    assert request.direct_urls == ["https://u"]
