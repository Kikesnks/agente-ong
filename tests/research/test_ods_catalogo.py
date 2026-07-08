"""
Tests de R25 (T25/T29): catálogo oficial de los 17 ODS del investigador.

A diferencia de R24 (ods_vocabulary.py), este módulo NO tiene fallback: todo
fallo de carga o de estructura debe lanzar ValueError con mensaje claro.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agente_ong.research.ods_catalogo import load_ods_catalogo


# --- Carga correcta: YAML real del proyecto ---


def test_load_ods_catalogo_reads_real_project_yaml() -> None:
    real_yaml = Path("src/agente_ong/research/ods_catalogo.yaml")

    result = load_ods_catalogo(real_yaml)

    assert len(result) == 17
    for entry in result:
        assert isinstance(entry["numero"], int)
        assert isinstance(entry["nombre"], str)
        assert entry["nombre"]


# --- YAML ausente ---


def test_load_ods_catalogo_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "no_existe.yaml"

    with pytest.raises(ValueError, match="No se pudo cargar ods_catalogo.yaml"):
        load_ods_catalogo(missing)


# --- YAML corrupto (sintaxis inválida) ---


def test_load_ods_catalogo_malformed_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "malo.yaml"
    # YAML inválido: comilla sin cerrar, indentación rota.
    bad.write_text("ods:\n  - unclosed \"quote\n:invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="No se pudo cargar ods_catalogo.yaml"):
        load_ods_catalogo(bad)


# --- YAML sin clave "ods" ---


def test_load_ods_catalogo_missing_ods_key_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / "sin_ods.yaml"
    yaml_file.write_text("otra_clave:\n  - 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="falta la clave 'ods'"):
        load_ods_catalogo(yaml_file)


# --- YAML con distinto número de elementos (16 y 18) ---


def _build_yaml_with_n_entries(n: int) -> str:
    lines = ["ods:"]
    for i in range(1, n + 1):
        lines.append(f'  - numero: {i}\n    nombre: "ODS {i}"')
    return "\n".join(lines) + "\n"


def test_load_ods_catalogo_with_16_entries_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / "dieciseis.yaml"
    yaml_file.write_text(_build_yaml_with_n_entries(16), encoding="utf-8")

    with pytest.raises(
        ValueError, match="debe contener exactamente 17 objetivos, se encontraron 16"
    ):
        load_ods_catalogo(yaml_file)


def test_load_ods_catalogo_with_18_entries_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / "dieciocho.yaml"
    yaml_file.write_text(_build_yaml_with_n_entries(18), encoding="utf-8")

    with pytest.raises(
        ValueError, match="debe contener exactamente 17 objetivos, se encontraron 18"
    ):
        load_ods_catalogo(yaml_file)


# --- Elemento sin "numero" o sin "nombre" ---


def test_load_ods_catalogo_entry_missing_nombre_raises(tmp_path: Path) -> None:
    lines = ["ods:"]
    for i in range(1, 18):
        if i == 5:
            lines.append(f"  - numero: {i}")  # falta "nombre"
        else:
            lines.append(f'  - numero: {i}\n    nombre: "ODS {i}"')
    yaml_file = tmp_path / "sin_nombre.yaml"
    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="el elemento 5 de 'ods'"):
        load_ods_catalogo(yaml_file)


def test_load_ods_catalogo_entry_missing_numero_raises(tmp_path: Path) -> None:
    lines = ["ods:"]
    for i in range(1, 18):
        if i == 12:
            lines.append(f'  - nombre: "ODS {i}"')  # falta "numero"
        else:
            lines.append(f'  - numero: {i}\n    nombre: "ODS {i}"')
    yaml_file = tmp_path / "sin_numero.yaml"
    yaml_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="el elemento 12 de 'ods'"):
        load_ods_catalogo(yaml_file)
