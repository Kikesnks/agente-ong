"""
Tests de R24: vocabulario ODS del investigador.

Cubre R24.1 (carga desde YAML), R24.2 (queries combinan término ODS con
vocabulario base de convocatoria), R24.3 (3 categorías), R24.4 (fallback si
el YAML falla) y el tope operativo de 5 queries ODS por ciclo.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agente_ong.research.ods_vocabulary import (
    FALLBACK_VOCABULARY,
    REQUIRED_CATEGORIES,
    load_ods_vocabulary,
)
from agente_ong.research.graph import ResearchGraph
from agente_ong.research.models import ResearchRequest


# --- R24.1: los términos del YAML quedan disponibles en memoria ---


def test_load_ods_vocabulary_returns_dict_with_three_categories(tmp_path: Path) -> None:
    yaml_content = """
ods_generales:
  - "termino uno"
cooperacion_espanola:
  - "termino dos"
enfoques_transversales:
  - "termino tres"
"""
    yaml_file = tmp_path / "ods.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    result = load_ods_vocabulary(yaml_file)

    assert set(result.keys()) == set(REQUIRED_CATEGORIES)
    assert result["ods_generales"] == ["termino uno"]
    assert result["cooperacion_espanola"] == ["termino dos"]
    assert result["enfoques_transversales"] == ["termino tres"]


# --- R24.2: queries combinan término ODS con vocabulario base de convocatoria ---


def test_derive_queries_ods_are_anchored_with_convocatoria() -> None:
    request = ResearchRequest(mode="calls", query_terms=["agua", "salud mental"])
    texts = [q.text for q in ResearchGraph._derive_queries(request)]

    # Todas las queries que NO son base deben empezar por "convocatoria "
    # (ancla obligatoria de R24.2). Las 2 primeras son base; el resto son ODS.
    ods_queries = texts[2:]
    assert len(ods_queries) > 0, "Debe generar al menos una query ODS"
    for q in ods_queries:
        assert q.startswith("convocatoria "), f"Query ODS sin ancla: {q!r}"


# --- R24.3: el parser lee las 3 categorías correctamente ---


def test_load_ods_vocabulary_reads_real_project_yaml() -> None:
    # El YAML real del proyecto debe cargarse y tener las 3 categorías con contenido.
    real_yaml = Path("src/agente_ong/research/ods_vocabulary.yaml")
    result = load_ods_vocabulary(real_yaml)

    assert set(result.keys()) == set(REQUIRED_CATEGORIES)
    assert len(result["ods_generales"]) > 0
    assert len(result["cooperacion_espanola"]) > 0
    # enfoques_transversales puede estar vacío en el fallback, pero en el YAML
    # real debe tener términos:
    assert len(result["enfoques_transversales"]) > 0


# --- R24.4: YAML ausente → fallback + log ---


def test_load_ods_vocabulary_missing_file_uses_fallback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "no_existe.yaml"

    with caplog.at_level(logging.WARNING, logger="agente_ong.research.ods_vocabulary"):
        result = load_ods_vocabulary(missing)

    assert result == FALLBACK_VOCABULARY
    assert any("no encontrado" in rec.message for rec in caplog.records)


# --- R24.4: YAML mal formado → fallback + log ---


def test_load_ods_vocabulary_malformed_uses_fallback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad = tmp_path / "malo.yaml"
    # YAML inválido: dos puntos sin cerrar, indentación rota.
    bad.write_text("ods_generales:\n  - unclosed \"quote\n:invalid", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="agente_ong.research.ods_vocabulary"):
        result = load_ods_vocabulary(bad)

    assert result == FALLBACK_VOCABULARY
    assert any("mal formado" in rec.message for rec in caplog.records)


# --- Tope operativo: máximo 5 queries ODS por ciclo ---


def test_derive_queries_ods_are_capped_at_five() -> None:
    request = ResearchRequest(mode="calls", query_terms=["agua", "salud mental"])
    texts = [q.text for q in ResearchGraph._derive_queries(request)]

    ods_queries = [t for t in texts if t.startswith("convocatoria ")]
    # "convocatoria" también podría aparecer como prefijo casual en queries
    # base si el usuario lo pusiera en query_terms; aquí query_terms no lo
    # incluye, así que todas las que empiecen por "convocatoria " son ODS.
    assert len(ods_queries) <= 5, f"Se generaron {len(ods_queries)} queries ODS, máximo 5"
