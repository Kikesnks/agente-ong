"""Tests de R1: contenedor AlineacionEstrategica."""
from __future__ import annotations

from dataclasses import asdict

from agente_ong.research.alignment import AlineacionEstrategica


def test_defaults_son_listas_vacias() -> None:
    alineacion = AlineacionEstrategica()

    assert alineacion.ods == []
    assert alineacion.prioridades_geograficas == []
    assert alineacion.enfoques_transversales == []
    assert alineacion.sectores_plan_director == []


def test_creacion_con_los_cuatro_campos_poblados_se_preserva_integra() -> None:
    alineacion = AlineacionEstrategica(
        ods=[3, 5],
        prioridades_geograficas=["América Latina y el Caribe"],
        enfoques_transversales=["Enfoque de derechos humanos"],
        sectores_plan_director=["Gobernabilidad democrática"],
    )

    assert alineacion.ods == [3, 5]
    assert alineacion.prioridades_geograficas == ["América Latina y el Caribe"]
    assert alineacion.enfoques_transversales == ["Enfoque de derechos humanos"]
    assert alineacion.sectores_plan_director == ["Gobernabilidad democrática"]


def test_ronda_serialize_deserialize_preserva_las_cuatro_listas_pobladas() -> None:
    original = AlineacionEstrategica(
        ods=[3, 5],
        prioridades_geograficas=["Norte de África"],
        enfoques_transversales=["Enfoque de construcción de paz"],
        sectores_plan_director=["Agua y saneamiento"],
    )

    data = asdict(original)
    reconstruido = AlineacionEstrategica(**data)

    assert reconstruido == original


def test_ronda_serialize_deserialize_preserva_las_cuatro_listas_vacias() -> None:
    original = AlineacionEstrategica()

    data = asdict(original)
    reconstruido = AlineacionEstrategica(**data)

    assert reconstruido == original
    assert data == {
        "ods": [],
        "prioridades_geograficas": [],
        "enfoques_transversales": [],
        "sectores_plan_director": [],
    }
