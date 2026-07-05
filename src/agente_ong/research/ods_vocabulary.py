"""
Carga del vocabulario ODS (R24) desde YAML con fallback embebido.

Si el archivo YAML falta o está mal formado, se usa un vocabulario de reserva
embebido en código (5 términos). El sistema nunca se detiene por un error de
configuración de vocabulario (R24.4).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import yaml

logger = logging.getLogger(__name__)

# Categorías obligatorias que debe contener el YAML (R24.3).
REQUIRED_CATEGORIES = ("ods_generales", "cooperacion_espanola", "enfoques_transversales")

# Fallback embebido: se usa si el YAML falla (R24.4).
# 5 términos más generales, distribuidos en las mismas 3 categorías para
# mantener una interfaz uniforme con el caso del YAML válido.
FALLBACK_VOCABULARY: Dict[str, List[str]] = {
    "ods_generales": [
        "Agenda 2030",
        "ODS",
        "Objetivos de Desarrollo Sostenible",
    ],
    "cooperacion_espanola": [
        "Plan Director cooperación española",
        "subvenciones 0,7%",
    ],
    "enfoques_transversales": [],
}


def load_ods_vocabulary(path: Path | str) -> Dict[str, List[str]]:
    """
    Carga el vocabulario ODS desde un archivo YAML.

    Devuelve un diccionario con 3 claves fijas (ods_generales,
    cooperacion_espanola, enfoques_transversales), cada una con una lista
    de términos.

    Si el archivo falta, no es YAML válido, o no contiene la estructura
    esperada, registra el problema en el log y devuelve FALLBACK_VOCABULARY.
    """
    yaml_path = Path(path)

    if not yaml_path.exists():
        logger.warning(
            "Archivo YAML de vocabulario ODS no encontrado en %s. Se usa fallback embebido.",
            yaml_path,
        )
        return dict(FALLBACK_VOCABULARY)

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        logger.warning(
            "Archivo YAML de vocabulario ODS mal formado (%s): %s. Se usa fallback embebido.",
            yaml_path,
            exc,
        )
        return dict(FALLBACK_VOCABULARY)

    if not isinstance(data, dict):
        logger.warning(
            "El YAML de vocabulario ODS no contiene un diccionario en la raíz (%s). Se usa fallback embebido.",
            yaml_path,
        )
        return dict(FALLBACK_VOCABULARY)

    missing = [cat for cat in REQUIRED_CATEGORIES if cat not in data]
    if missing:
        logger.warning(
            "Al YAML de vocabulario ODS le faltan categorías %s (%s). Se usa fallback embebido.",
            missing,
            yaml_path,
        )
        return dict(FALLBACK_VOCABULARY)

    # Estructura válida: normalizar a listas de strings y devolver solo las
    # categorías esperadas (ignorando claves extra que puedan aparecer).
    result: Dict[str, List[str]] = {}
    for cat in REQUIRED_CATEGORIES:
        terms = data.get(cat) or []
        if not isinstance(terms, list):
            logger.warning(
                "La categoría '%s' en el YAML no es una lista (%s). Se usa fallback embebido.",
                cat,
                yaml_path,
            )
            return dict(FALLBACK_VOCABULARY)
        result[cat] = [str(t) for t in terms]

    return result
