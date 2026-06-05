"""Configuración del agente investigador.

`ResearchConfig` agrupa toda la configuración inyectable del módulo: claves de API de las
fuentes, ruta de almacenamiento de material de entrenamiento y límites de la investigación.
Se construye preferentemente con `ResearchConfig.from_env()`, que lee variables de entorno
— las claves de API nunca se hardcodean ni se versionan (ver `.claude/steering/tech.md` y los
requisitos de seguridad de la spec).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Valores por defecto de los límites de investigación. Prioridad calidad > velocidad, pero
# acotada para evitar bucles o costes descontrolados (ver NFR Performance de la spec).
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_QUERIES = 30
DEFAULT_STALENESS_DAYS = 30

# Ruta por defecto del material de entrenamiento (relativa a la raíz del proyecto).
DEFAULT_ENTRENAMIENTO_PATH = Path("RECURSOS") / "ENTRENAMIENTO"

# Ruta por defecto de la base de datos de persistencia (carpeta oculta interna de la app).
DEFAULT_DB_PATH = Path(".data") / "agente_ong.db"


def _env_int(name: str, default: int) -> int:
    """Lee un entero de una variable de entorno; usa `default` si falta o es inválida."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class ResearchConfig:
    """Configuración inyectable del agente investigador.

    Las claves de API son opcionales: una fuente sin su clave correspondiente simplemente no
    estará operativa, pero el resto de la investigación puede continuar (ver Reliability).
    """

    # --- Claves de API de las fuentes (None => fuente no configurada) ---
    tavily_api_key: str | None = None
    firecrawl_api_key: str | None = None
    bdns_api_key: str | None = None
    ted_api_key: str | None = None

    # --- Almacenamiento de material de entrenamiento ---
    entrenamiento_path: Path = field(
        default_factory=lambda: DEFAULT_ENTRENAMIENTO_PATH
    )

    # --- Persistencia (base de datos SQLite) ---
    # Por defecto persiste en DEFAULT_DB_PATH. `db_path=None` => modo efímero (InMemoryStore).
    db_path: Path | None = field(default_factory=lambda: DEFAULT_DB_PATH)

    # --- Límites de la investigación ---
    max_depth: int = DEFAULT_MAX_DEPTH
    max_pages: int = DEFAULT_MAX_PAGES
    max_queries: int = DEFAULT_MAX_QUERIES
    staleness_days: int = DEFAULT_STALENESS_DAYS

    def __post_init__(self) -> None:
        # Normaliza las rutas a Path por si se inyectan como str.
        if not isinstance(self.entrenamiento_path, Path):
            self.entrenamiento_path = Path(self.entrenamiento_path)
        # db_path admite None (modo efímero); si es str se normaliza a Path.
        if self.db_path is not None and not isinstance(self.db_path, Path):
            self.db_path = Path(self.db_path)

    @classmethod
    def from_env(cls) -> "ResearchConfig":
        """Construye la configuración a partir de variables de entorno.

        Variables reconocidas:
          - TAVILY_API_KEY, FIRECRAWL_API_KEY, BDNS_API_KEY, TED_API_KEY
          - RECURSOS_ENTRENAMIENTO_PATH (ruta del material de entrenamiento)
          - RESEARCH_DB_PATH (ruta de la base de datos de persistencia; por defecto persistente)
          - RESEARCH_MAX_DEPTH, RESEARCH_MAX_PAGES, RESEARCH_MAX_QUERIES,
            RESEARCH_STALENESS_DAYS (límites; enteros)
        """
        entrenamiento = os.environ.get("RECURSOS_ENTRENAMIENTO_PATH")
        db_path = os.environ.get("RESEARCH_DB_PATH")
        return cls(
            tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            firecrawl_api_key=os.environ.get("FIRECRAWL_API_KEY"),
            bdns_api_key=os.environ.get("BDNS_API_KEY"),
            ted_api_key=os.environ.get("TED_API_KEY"),
            entrenamiento_path=(
                Path(entrenamiento) if entrenamiento else DEFAULT_ENTRENAMIENTO_PATH
            ),
            db_path=(Path(db_path) if db_path else DEFAULT_DB_PATH),
            max_depth=_env_int("RESEARCH_MAX_DEPTH", DEFAULT_MAX_DEPTH),
            max_pages=_env_int("RESEARCH_MAX_PAGES", DEFAULT_MAX_PAGES),
            max_queries=_env_int("RESEARCH_MAX_QUERIES", DEFAULT_MAX_QUERIES),
            staleness_days=_env_int("RESEARCH_STALENESS_DAYS", DEFAULT_STALENESS_DAYS),
        )
