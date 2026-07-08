"""
Tests de R24: vocabulario ODS del investigador (carga desde YAML).

Cubre R24.1 (carga desde YAML), R24.3 (3 categorías) y R24.4 (fallback si el
YAML falla). Los tests que probaban la integración con `_derive_queries()`
(anclaje "convocatoria " y tope de 5 por ciclo) se eliminaron en R25: ese
comportamiento automático ya no existe, sustituido por la selección explícita
del usuario (ver `test_graph_flow.py` y decisión B1 en `requirements.md`,
R25.3). `load_ods_vocabulary` en sí sigue vigente como fallback documentado
en R25.3 (candidato a limpieza, decisión pendiente #17).
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
