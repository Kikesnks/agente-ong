"""Mapeo de los controles de la UI a la entrada del investigador (R8/R9/R10).

`build()` traduce lo que el usuario eligió en pantalla (términos, ámbito, nivel de
profundidad, año mínimo, fuentes activas, URLs directas) a la pareja
`(ResearchConfig, ResearchRequest)` que consume `Investigador`. La profundidad viaja como
override en el request (`max_depth`/`max_pages`, ya soportados); `min_year` viaja en la
config porque las fuentes se construyen con él (ver decisión de diseño en design.md).

Los VALORES de los presets son provisionales (decisión histórica sobre presets, resuelta 2026-06): "normal" está
anclado a los defaults actuales del módulo (DEFAULT_MAX_DEPTH/DEFAULT_MAX_PAGES), "rápida"
por debajo y "exhaustiva" por encima (R8.2: valores crecientes).
"""

from __future__ import annotations

from dataclasses import replace

from agente_ong.research.config import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, ResearchConfig
from agente_ong.research.models import ResearchRequest, Scope

# Nivel de profundidad -> (max_depth, max_pages). "normal" = defaults del módulo (sin
# esfuerzo extra ni recorte); los demás escalan hacia abajo/arriba (R8.2).
DEPTH_PRESETS: dict[str, tuple[int, int]] = {
    "rápida": (1, 10),
    "normal": (DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES),  # (3, 50)
    "exhaustiva": (5, 150),
}

DEFAULT_DEPTH_LEVEL = "normal"  # R8.3

# Contexto de búsqueda por defecto (R13.3) cuando el proyecto no define el suyo. Vive aquí
# y se resuelve EN EL LANZAMIENTO (no se persiste en projects): cambiarlo afecta a todos
# los proyectos sin contexto propio, sin migrar datos.
DEFAULT_SEARCH_CONTEXT = "convocatoria de subvención para organizaciones sin ánimo de lucro"


def build(
    base_config: ResearchConfig,
    *,
    terms: list[str],
    scope: Scope | None = None,
    depth_level: str = DEFAULT_DEPTH_LEVEL,
    min_year: int | None = None,
    enabled_sources: set[str] | None = None,
    direct_urls: list[str] | None = None,
    search_context: str | None = None,
) -> tuple[ResearchConfig, ResearchRequest]:
    """Construye la config y el request de una investigación desde los controles de la UI.

    - `depth_level`: clave de `DEPTH_PRESETS` ("normal" si no se indica, R8.3); un nivel
      desconocido lanza `ValueError` (la UI solo ofrece los tres, R8.1).
    - `enabled_sources is None` => todas las fuentes; un set vacío SIN URLs directas no
      tiene nada que investigar y se rechaza antes de crear el job (R9.5).
    - `min_year` se aplica sobre una COPIA de la config (la base no se muta).
    - `search_context` vacío o None => `DEFAULT_SEARCH_CONTEXT` (R13.3); el valor normal es
      el `search_context` del proyecto (R13.2).
    """
    if depth_level not in DEPTH_PRESETS:
        raise ValueError(
            f"Nivel de profundidad desconocido: {depth_level!r}. "
            f"Opciones: {', '.join(DEPTH_PRESETS)}."
        )
    urls = list(direct_urls or [])
    if enabled_sources is not None and not enabled_sources and not urls:
        raise ValueError("Activa al menos una fuente o indica una URL directa.")

    max_depth, max_pages = DEPTH_PRESETS[depth_level]
    config = replace(base_config, min_year=min_year)
    request = ResearchRequest(
        mode="calls",
        query_terms=list(terms),
        scope=scope if scope is not None else Scope(),
        max_depth=max_depth,
        max_pages=max_pages,
        search_context=(search_context or "").strip() or DEFAULT_SEARCH_CONTEXT,
        enabled_sources=set(enabled_sources) if enabled_sources is not None else None,
        direct_urls=urls,
    )
    return config, request
