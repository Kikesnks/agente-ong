"""
Carga de los catálogos de alineación estratégica (R2/R3/R4) desde YAML.

Estos catálogos NO tienen fallback embebido: si un YAML falta, no es válido
o no contiene la estructura/recuento esperado, se lanza ValueError explícito
(mismo patrón sin-fallback que research/ods_catalogo.py). Los catálogos son
la fuente de la taxonomía cerrada del Plan Director 2024-2027 que consumen
el parser y el prompt de extracción; un catálogo incompleto o corrupto no
debe pasar desapercibido.

Dos de los tres catálogos son listas planas de valores (prioridades,
enfoques) y el tercero (sectores) es una jerarquía de transiciones; por eso
se comparten los helpers de carga/validación de YAML pero se exponen
funciones públicas independientes por catálogo en vez de un loader genérico
único.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

_CATALOGOS_DIR = Path(__file__).resolve().parent / "catalogos"
_PRIORIDADES_PATH = _CATALOGOS_DIR / "prioridades_geograficas.yaml"
_ENFOQUES_PATH = _CATALOGOS_DIR / "enfoques_transversales.yaml"
_SECTORES_PATH = _CATALOGOS_DIR / "sectores_plan_director.yaml"

EXPECTED_PRIORIDADES = 4
EXPECTED_ENFOQUES = 6
EXPECTED_SECTORES = 13


def _load_yaml(path: Path, nombre_archivo: str) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise ValueError(f"No se pudo cargar {nombre_archivo}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"No se pudo cargar {nombre_archivo}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"No se pudo cargar {nombre_archivo}: el YAML no tiene una raíz de tipo mapping"
        )

    return data


def _cargar_lista_valores(path: Path, nombre_archivo: str, expected_count: int) -> List[str]:
    data = _load_yaml(path, nombre_archivo)

    if "valores" not in data:
        raise ValueError(
            f"No se pudo cargar {nombre_archivo}: falta la clave 'valores' en la raíz del YAML"
        )

    valores = data["valores"]
    if not isinstance(valores, list) or not all(isinstance(v, str) for v in valores):
        raise ValueError(f"No se pudo cargar {nombre_archivo}: 'valores' debe ser una lista de strings")

    if len(valores) != expected_count:
        raise ValueError(
            f"El catálogo {nombre_archivo} debe contener exactamente {expected_count} valores, "
            f"se encontraron {len(valores)}"
        )

    if len(valores) != len(set(valores)):
        raise ValueError(f"El catálogo {nombre_archivo} contiene valores duplicados")

    return list(valores)


def cargar_prioridades_geograficas() -> List[str]:
    """Devuelve la lista literal de las 4 prioridades geográficas del Plan Director."""
    return _cargar_lista_valores(_PRIORIDADES_PATH, "prioridades_geograficas.yaml", EXPECTED_PRIORIDADES)


def cargar_enfoques_transversales() -> List[str]:
    """Devuelve la lista literal de los 6 enfoques transversales del Plan Director."""
    return _cargar_lista_valores(_ENFOQUES_PATH, "enfoques_transversales.yaml", EXPECTED_ENFOQUES)


def _cargar_transiciones() -> List[Dict[str, Any]]:
    data = _load_yaml(_SECTORES_PATH, "sectores_plan_director.yaml")

    if "transiciones" not in data or not isinstance(data["transiciones"], list):
        raise ValueError(
            "No se pudo cargar sectores_plan_director.yaml: falta la clave 'transiciones' "
            "en la raíz del YAML"
        )

    for i, transicion in enumerate(data["transiciones"], start=1):
        if not isinstance(transicion, dict) or "nombre" not in transicion or "sectores" not in transicion:
            raise ValueError(
                f"No se pudo cargar sectores_plan_director.yaml: la transición {i} no tiene "
                "las claves 'nombre' y 'sectores'"
            )
        if not isinstance(transicion["sectores"], list):
            raise ValueError(
                f"No se pudo cargar sectores_plan_director.yaml: 'sectores' de la transición {i} "
                "no es una lista"
            )
        for j, sector in enumerate(transicion["sectores"], start=1):
            if not isinstance(sector, dict) or "nombre" not in sector:
                raise ValueError(
                    f"No se pudo cargar sectores_plan_director.yaml: el sector {j} de la "
                    f"transición {i} no tiene la clave 'nombre'"
                )

    return data["transiciones"]


def cargar_sectores_plan_director() -> List[str]:
    """Devuelve la lista de nombres de los 13 sectores del Plan Director."""
    transiciones = _cargar_transiciones()

    nombres: List[str] = [
        str(sector["nombre"]) for transicion in transiciones for sector in transicion["sectores"]
    ]

    if len(nombres) != EXPECTED_SECTORES:
        raise ValueError(
            "El catálogo sectores_plan_director.yaml debe contener exactamente "
            f"{EXPECTED_SECTORES} sectores, se encontraron {len(nombres)}"
        )

    if len(nombres) != len(set(nombres)):
        raise ValueError("El catálogo sectores_plan_director.yaml contiene sectores duplicados")

    return nombres


def obtener_transicion_de_sector(sector: str) -> str:
    """Dado un nombre de sector válido, devuelve el nombre de su transición.

    Lanza ValueError si el sector no existe en el catálogo.
    """
    transiciones = _cargar_transiciones()

    for transicion in transiciones:
        for entry in transicion["sectores"]:
            if entry["nombre"] == sector:
                return str(transicion["nombre"])

    raise ValueError(f"El sector '{sector}' no existe en el catálogo de sectores del Plan Director")
