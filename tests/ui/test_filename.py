"""Tests de src/agente_ong/ui/filename.py (decisión #25: nombrado de informes)."""

from __future__ import annotations

from datetime import date

import pytest

from agente_ong.ui.filename import build_report_filename, slugify_project_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Proyecto Educación", "proyecto_educacion"),
        ("Niño Ñandú Áéíóú", "nino_nandu_aeiou"),
        ("PROYECTO", "proyecto"),
        ("proyecto/2026 (v2)", "proyecto_2026_v2"),
        ("a   b", "a_b"),
    ],
)
def test_slugify_project_name_happy_paths(name: str, expected: str) -> None:
    assert slugify_project_name(name, fallback="proj-123") == expected


def test_slugify_project_name_empty_uses_fallback() -> None:
    assert slugify_project_name("", fallback="proj-123") == "proj_123"


def test_slugify_project_name_only_symbols_uses_fallback() -> None:
    assert slugify_project_name("!!!", fallback="proj-123") == "proj_123"


def test_slugify_project_name_non_latin_uses_fallback() -> None:
    assert slugify_project_name("Проект", fallback="proj-123") == "proj_123"


def test_slugify_project_name_fallback_also_empty_defaults_to_proyecto() -> None:
    assert slugify_project_name("", fallback="???") == "proyecto"


def test_slugify_project_name_truncates_to_max_length() -> None:
    long_name = "palabra_" * 20  # 160 chars
    slug = slugify_project_name(long_name, fallback="proj-123")
    assert len(slug) <= 60
    assert not slug.endswith("_")


def test_build_report_filename_summary() -> None:
    result = build_report_filename(
        project_slug="proyecto_educacion", created_at=date(2026, 7, 16), kind="summary"
    )
    assert result == "informe_proyecto_educacion_2026-07-16.md"


def test_build_report_filename_detailed() -> None:
    result = build_report_filename(
        project_slug="proyecto_educacion", created_at=date(2026, 7, 16), kind="detailed"
    )
    assert result == "informe_detallado_proyecto_educacion_2026-07-16.md"


def test_build_report_filename_date_always_iso_format() -> None:
    result = build_report_filename(
        project_slug="x", created_at=date(2026, 1, 5), kind="summary"
    )
    assert "2026-01-05" in result
