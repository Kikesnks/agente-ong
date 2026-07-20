"""Tests de R5: parser de la respuesta LLM de alineación estratégica contra catálogos."""
from __future__ import annotations

import json

import pytest

from agente_ong.research.alignment_parser import AlignmentParseError, parsear_alineacion


def _payload(**overrides) -> str:
    base = {
        "ods": [],
        "prioridades_geograficas": [],
        "enfoques_transversales": [],
        "sectores_plan_director": [],
    }
    base.update(overrides)
    return json.dumps(base)


# --- Caso feliz ---


def test_caso_feliz_todos_los_valores_validos() -> None:
    respuesta = _payload(
        ods=[3, 5],
        prioridades_geograficas=["América Latina y el Caribe"],
        enfoques_transversales=["Enfoque de derechos humanos"],
        sectores_plan_director=["Gobernabilidad democrática"],
    )

    resultado = parsear_alineacion(respuesta)

    assert resultado.ods == [3, 5]
    assert resultado.prioridades_geograficas == ["América Latina y el Caribe"]
    assert resultado.enfoques_transversales == ["Enfoque de derechos humanos"]
    assert resultado.sectores_plan_director == ["Gobernabilidad democrática"]


# --- Valores fuera de catálogo (mezcla válidos/inválidos) ---


def test_prioridades_geograficas_fuera_de_catalogo_se_descartan(caplog: pytest.LogCaptureFixture) -> None:
    respuesta = _payload(
        prioridades_geograficas=["América Latina y el Caribe", "Europa Occidental"]
    )

    with caplog.at_level("WARNING"):
        resultado = parsear_alineacion(respuesta)

    assert resultado.prioridades_geograficas == ["América Latina y el Caribe"]
    assert "Europa Occidental" in caplog.text


def test_enfoques_transversales_fuera_de_catalogo_se_descartan() -> None:
    respuesta = _payload(
        enfoques_transversales=["Enfoque de derechos humanos", "Enfoque inventado"]
    )

    resultado = parsear_alineacion(respuesta)

    assert resultado.enfoques_transversales == ["Enfoque de derechos humanos"]


def test_sectores_plan_director_fuera_de_catalogo_se_descartan() -> None:
    respuesta = _payload(
        sectores_plan_director=["Gobernabilidad democrática", "Sector inventado"]
    )

    resultado = parsear_alineacion(respuesta)

    assert resultado.sectores_plan_director == ["Gobernabilidad democrática"]


# --- ODS fuera de rango ---


def test_ods_fuera_de_rango_se_descartan() -> None:
    respuesta = _payload(ods=[3, 18, 0, -1, 5])

    resultado = parsear_alineacion(respuesta)

    assert resultado.ods == [3, 5]


# --- Duplicados: colapsados preservando orden de primera aparición ---


def test_duplicados_se_colapsan_preservando_orden() -> None:
    respuesta = _payload(
        ods=[5, 3, 5, 3],
        prioridades_geograficas=["Norte de África", "Norte de África"],
        enfoques_transversales=[
            "Enfoque de construcción de paz",
            "Enfoque de diversidad cultural",
            "Enfoque de construcción de paz",
        ],
        sectores_plan_director=["Agua y saneamiento", "Agua y saneamiento"],
    )

    resultado = parsear_alineacion(respuesta)

    assert resultado.ods == [5, 3]
    assert resultado.prioridades_geograficas == ["Norte de África"]
    assert resultado.enfoques_transversales == [
        "Enfoque de construcción de paz",
        "Enfoque de diversidad cultural",
    ]
    assert resultado.sectores_plan_director == ["Agua y saneamiento"]


# --- JSON malformado ---


def test_json_malformado_lanza_alignment_parse_error() -> None:
    with pytest.raises(AlignmentParseError):
        parsear_alineacion("{esto no es json")


# --- Estructura incorrecta ---


def test_respuesta_no_es_objeto_json_lanza_alignment_parse_error() -> None:
    with pytest.raises(AlignmentParseError):
        parsear_alineacion(json.dumps([1, 2, 3]))


def test_falta_un_campo_lanza_alignment_parse_error() -> None:
    payload = json.dumps(
        {
            "ods": [],
            "prioridades_geograficas": [],
            "enfoques_transversales": [],
            # falta 'sectores_plan_director'
        }
    )

    with pytest.raises(AlignmentParseError, match="sectores_plan_director"):
        parsear_alineacion(payload)


def test_campo_con_tipo_incorrecto_lanza_alignment_parse_error() -> None:
    respuesta = _payload(ods="3, 5")  # debería ser una lista, no un string

    with pytest.raises(AlignmentParseError, match="ods"):
        parsear_alineacion(respuesta)


# --- Tolerancia a code-fence Markdown (qwen2.5:7b envuelve el JSON siempre) ---


def test_respuesta_con_fence_json_parsea_bien() -> None:
    payload = _payload(ods=[3, 5])
    respuesta = f"```json\n{payload}\n```"

    resultado = parsear_alineacion(respuesta)

    assert resultado.ods == [3, 5]


def test_respuesta_con_fence_sin_lenguaje_parsea_bien() -> None:
    payload = _payload(ods=[3, 5])
    respuesta = f"```\n{payload}\n```"

    resultado = parsear_alineacion(respuesta)

    assert resultado.ods == [3, 5]


def test_respuesta_sin_fence_sigue_parseando_bien() -> None:
    """Retrocompatible: un JSON pelado (sin envoltorio) sigue funcionando igual."""
    payload = _payload(ods=[3, 5])

    resultado = parsear_alineacion(payload)

    assert resultado.ods == [3, 5]


def test_respuesta_con_basura_antes_del_fence_lanza_alignment_parse_error() -> None:
    payload = _payload(ods=[3, 5])
    respuesta = f"Aquí tienes el resultado:\n```json\n{payload}\n```"

    with pytest.raises(AlignmentParseError):
        parsear_alineacion(respuesta)


def test_respuesta_con_basura_despues_del_fence_lanza_alignment_parse_error() -> None:
    payload = _payload(ods=[3, 5])
    respuesta = f"```json\n{payload}\n```\nEspero que te sirva."

    with pytest.raises(AlignmentParseError):
        parsear_alineacion(respuesta)
