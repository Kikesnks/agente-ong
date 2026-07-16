"""
Carga del catálogo oficial de los 17 ODS (R25) desde YAML.

Este módulo NO tiene fallback embebido: si el YAML falla al cargar o no
contiene los 17 objetivos esperados, se lanza una excepción explícita
(decisión B de R25). El
catálogo es la fuente de opciones de la multiselección obligatoria de la
UI (R25.1); un catálogo incompleto o corrupto no debe pasar desapercibido.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Union

import yaml

# Número de ODS oficiales que debe contener el catálogo.
EXPECTED_COUNT = 17

OdsEntry = Dict[str, Union[int, str]]


def load_ods_catalogo(path: Path | str) -> List[OdsEntry]:
    """
    Carga el catálogo de los 17 ODS desde un archivo YAML.

    Devuelve una lista de diccionarios con las claves "numero" (int) y
    "nombre" (str), uno por cada ODS.

    Lanza ValueError si el archivo falta, no es YAML válido, no contiene
    la clave "ods", o esta no tiene exactamente 17 elementos bien formados.
    """
    yaml_path = Path(path)

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise ValueError(f"No se pudo cargar ods_catalogo.yaml: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"No se pudo cargar ods_catalogo.yaml: {exc}") from exc

    if not isinstance(data, dict) or "ods" not in data:
        raise ValueError(
            "No se pudo cargar ods_catalogo.yaml: falta la clave 'ods' en la raíz del YAML"
        )

    entries = data["ods"]
    if not isinstance(entries, list) or len(entries) != EXPECTED_COUNT:
        found = len(entries) if isinstance(entries, list) else 0
        raise ValueError(
            f"El catálogo ODS debe contener exactamente {EXPECTED_COUNT} objetivos, "
            f"se encontraron {found}"
        )

    catalogo: List[OdsEntry] = []
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or "numero" not in entry or "nombre" not in entry:
            raise ValueError(
                f"No se pudo cargar ods_catalogo.yaml: el elemento {i} de 'ods' "
                "no tiene las claves 'numero' y 'nombre'"
            )
        catalogo.append({"numero": int(entry["numero"]), "nombre": str(entry["nombre"])})

    return catalogo
