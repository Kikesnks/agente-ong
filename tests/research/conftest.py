"""Fixtures compartidas de tests/research/."""

from __future__ import annotations

import pytest

from agente_ong.research.ods_catalogo import OdsEntry

# 3 ODS de ejemplo, suficientes para probar N->N sin acoplar los tests a los
# 17 ODS reales del catálogo (T24).
_SAMPLE_SELECTED_ODS: list[OdsEntry] = [
    {"numero": 1, "nombre": "Fin de la pobreza"},
    {"numero": 3, "nombre": "Salud y bienestar"},
    {"numero": 5, "nombre": "Igualdad de género"},
]


@pytest.fixture
def selected_ods() -> list[OdsEntry]:
    """ODS de ejemplo para pasar a `Investigador.run()` en tests de integración (R25)."""
    return list(_SAMPLE_SELECTED_ODS)
