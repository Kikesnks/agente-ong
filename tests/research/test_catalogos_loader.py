"""
Tests de R2/R3/R4: catálogos de alineación estratégica (Plan Director 2024-2027).

Este módulo NO tiene fallback: todo fallo de carga o de estructura debe
lanzar ValueError con mensaje claro (mismo patrón que research/ods_catalogo.py).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agente_ong.research import catalogos_loader
from agente_ong.research.catalogos_loader import (
    cargar_enfoques_transversales,
    cargar_prioridades_geograficas,
    cargar_sectores_plan_director,
    obtener_transicion_de_sector,
)

# --- Valores literales esperados, según design.md ---

_PRIORIDADES_ESPERADAS = [
    "América Latina y el Caribe",
    "Norte de África",
    "Oriente Próximo",
    "África Subsahariana",
]

_ENFOQUES_ESPERADOS = [
    "Enfoque de derechos humanos",
    "Enfoque feminista y de género",
    "Enfoque de lucha contra la pobreza y las desigualdades",
    "Enfoque de justicia climática y sostenibilidad medioambiental",
    "Enfoque de diversidad cultural",
    "Enfoque de construcción de paz",
]

_SECTORES_A_TRANSICION = {
    "Gobernabilidad democrática": "Transición social",
    "Salud global y sistemas sanitarios": "Transición social",
    "Seguridad alimentaria y lucha contra el hambre": "Transición social",
    "Educación equitativa, inclusiva y de calidad y formación a lo largo de la vida": "Transición social",
    "Igualdad de género y empoderamiento de todas las mujeres, niñas y adolescentes": "Transición social",
    "Cultura y desarrollo": "Transición social",
    "Lucha contra el cambio climático: adaptación y mitigación": "Transición ecológica",
    "Acceso a energías limpias": "Transición ecológica",
    "Promoción y protección de la biodiversidad": "Transición ecológica",
    "Agua y saneamiento": "Transición ecológica",
    "Desarrollo rural territorial y sistemas agroalimentarios sostenibles": "Transición económica",
    "Desarrollo económico inclusivo y sostenible": "Transición económica",
    "Digitalización para el desarrollo sostenible": "Transición económica",
}


# --- Carga correcta de los 3 catálogos reales del proyecto ---


def test_cargar_prioridades_geograficas() -> None:
    resultado = cargar_prioridades_geograficas()

    assert len(resultado) == 4
    assert resultado == _PRIORIDADES_ESPERADAS


def test_cargar_enfoques_transversales() -> None:
    resultado = cargar_enfoques_transversales()

    assert len(resultado) == 6
    assert resultado == _ENFOQUES_ESPERADOS


def test_cargar_sectores_plan_director() -> None:
    resultado = cargar_sectores_plan_director()

    assert len(resultado) == 13
    assert set(resultado) == set(_SECTORES_A_TRANSICION.keys())


# --- Ausencia de duplicados ---


def test_prioridades_geograficas_sin_duplicados() -> None:
    resultado = cargar_prioridades_geograficas()

    assert len(resultado) == len(set(resultado))


def test_enfoques_transversales_sin_duplicados() -> None:
    resultado = cargar_enfoques_transversales()

    assert len(resultado) == len(set(resultado))


def test_sectores_plan_director_sin_duplicados() -> None:
    resultado = cargar_sectores_plan_director()

    assert len(resultado) == len(set(resultado))


# --- obtener_transicion_de_sector: los 13 sectores + sector inventado ---


@pytest.mark.parametrize("sector, transicion_esperada", list(_SECTORES_A_TRANSICION.items()))
def test_obtener_transicion_de_sector(sector: str, transicion_esperada: str) -> None:
    assert obtener_transicion_de_sector(sector) == transicion_esperada


def test_obtener_transicion_de_sector_inventado_lanza_valueerror() -> None:
    with pytest.raises(ValueError, match="no existe en el catálogo"):
        obtener_transicion_de_sector("Sector que no existe en el Plan Director")


# --- Sin-fallback: YAML ausente, corrupto o con estructura/recuento inválidos ---


def test_cargar_prioridades_geograficas_archivo_ausente_lanza_valueerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(catalogos_loader, "_PRIORIDADES_PATH", tmp_path / "no_existe.yaml")

    with pytest.raises(ValueError, match="No se pudo cargar prioridades_geograficas.yaml"):
        cargar_prioridades_geograficas()


def test_cargar_enfoques_transversales_yaml_corrupto_lanza_valueerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = tmp_path / "malo.yaml"
    bad.write_text("valores:\n  - unclosed \"quote\n:invalid", encoding="utf-8")
    monkeypatch.setattr(catalogos_loader, "_ENFOQUES_PATH", bad)

    with pytest.raises(ValueError, match="No se pudo cargar enfoques_transversales.yaml"):
        cargar_enfoques_transversales()


def test_cargar_prioridades_geograficas_recuento_incorrecto_lanza_valueerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_file = tmp_path / "tres.yaml"
    yaml_file.write_text('valores:\n  - "A"\n  - "B"\n  - "C"\n', encoding="utf-8")
    monkeypatch.setattr(catalogos_loader, "_PRIORIDADES_PATH", yaml_file)

    with pytest.raises(ValueError, match="debe contener exactamente 4 valores, se encontraron 3"):
        cargar_prioridades_geograficas()


def test_cargar_enfoques_transversales_con_duplicados_lanza_valueerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_file = tmp_path / "duplicados.yaml"
    valores = '\n'.join(f'  - "Enfoque {i}"' for i in range(1, 6))
    yaml_file.write_text(f'valores:\n{valores}\n  - "Enfoque 1"\n', encoding="utf-8")
    monkeypatch.setattr(catalogos_loader, "_ENFOQUES_PATH", yaml_file)

    with pytest.raises(ValueError, match="contiene valores duplicados"):
        cargar_enfoques_transversales()


def test_cargar_sectores_plan_director_sin_clave_transiciones_lanza_valueerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_file = tmp_path / "sin_transiciones.yaml"
    yaml_file.write_text("otra_clave: []\n", encoding="utf-8")
    monkeypatch.setattr(catalogos_loader, "_SECTORES_PATH", yaml_file)

    with pytest.raises(ValueError, match="falta la clave 'transiciones'"):
        cargar_sectores_plan_director()


def test_cargar_sectores_plan_director_recuento_incorrecto_lanza_valueerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_file = tmp_path / "sectores_incompletos.yaml"
    yaml_file.write_text(
        'transiciones:\n'
        '  - nombre: "Transición social"\n'
        '    sectores:\n'
        '      - nombre: "Sector A"\n'
        '      - nombre: "Sector B"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(catalogos_loader, "_SECTORES_PATH", yaml_file)

    with pytest.raises(ValueError, match="debe contener exactamente 13 sectores, se encontraron 2"):
        cargar_sectores_plan_director()
