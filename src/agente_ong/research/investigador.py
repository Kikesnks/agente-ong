"""Fachada pública del agente investigador.

`Investigador` es el único punto de entrada del módulo y su superficie portable: se construye
con una `ResearchConfig` (y, opcionalmente, fuentes y store inyectados) y expone
`run(request) -> ResearchReport`. Internamente arma la capa de fuentes, el ledger, la política
de verificación, el limitador de profundidad y el collector, y ejecuta el grafo LangGraph.

Portabilidad (Requirement 7): el núcleo no depende de la UI ni del backend de persistencia,
que vive tras el puerto `ResearchStore` (patrón Ports & Adapters). Por defecto usa
`SqliteStore` (persistencia real del producto: recall entre sesiones en un archivo `.db`); con
`config.db_path=None` o inyectando un store usa `InMemoryStore` (modo efímero, para tests).
Cambiar de un modo a otro no toca el núcleo. Las fuentes por defecto se construyen con sus
claves desde la config (Requirement 7.2); se pueden sustituir inyectando otras (Requirement 7.3).

Cada `run()` usa un `SourceLedger` nuevo (vista en memoria limpia de esa investigación) pero
comparte el `ResearchStore`, de modo que las investigaciones previas reaparezcan como PISTAS
(no como URLs "ya vistas" en la investigación en curso).
"""

from __future__ import annotations

from agente_ong.research.collector import TrainingCollector
from agente_ong.research.config import ResearchConfig
from agente_ong.research.depth import DepthLimiter
from agente_ong.research.graph import ResearchGraph
from agente_ong.research.ledger import SourceLedger
from agente_ong.research.models import ResearchReport, ResearchRequest
from agente_ong.research.sources.base import SearchSource
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.store.memory import InMemoryStore
from agente_ong.research.verification import VerificationPolicy


class Investigador:
    """Punto de entrada portable del agente investigador."""

    def __init__(
        self,
        config: ResearchConfig,
        sources: list[SearchSource] | None = None,
        store: ResearchStore | None = None,
    ) -> None:
        self._config = config
        # Persistencia (prioridad: store inyectado > config.db_path):
        #   - store inyectado  -> se usa tal cual; lo gestiona quien lo creó.
        #   - config.db_path None -> InMemoryStore (modo efímero, sin persistencia).
        #   - config.db_path ruta -> SqliteStore (persistencia real del producto).
        if store is not None:
            self._store: ResearchStore = store
            self._owns_store = False
        elif config.db_path is None:
            self._store = InMemoryStore()
            self._owns_store = True
        else:
            # Import perezoso: no acoplar la fachada a sqlite cuando se inyecta otro store.
            from agente_ong.research.store.sqlite import SqliteStore

            self._store = SqliteStore(config.db_path)
            self._owns_store = True
        self._sources = sources if sources is not None else self._default_sources(config)
        # Colaboradores sin estado por investigación (se pueden compartir entre runs).
        self._policy = VerificationPolicy(config)
        self._limiter = DepthLimiter(config)
        self._collector = TrainingCollector(config, self._store)

    def close(self) -> None:
        """Cierra el store si lo creó esta fachada (libera la conexión SQLite y sus WAL)."""
        if self._owns_store:
            close = getattr(self._store, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> "Investigador":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def run(self, request: ResearchRequest) -> ResearchReport:
        """Ejecuta una investigación completa y devuelve su informe.

        Usa un ledger nuevo (vista en memoria limpia) sobre el store compartido, construye el
        grafo y lo invoca. El `compile_report` final persiste el ledger en el store.
        """
        ledger = SourceLedger(self._store)
        graph = ResearchGraph(
            sources=self._sources,
            ledger=ledger,
            policy=self._policy,
            limiter=self._limiter,
            collector=self._collector,
            config=self._config,
        )
        app = graph.build()
        final = app.invoke({"request": request})
        return final["report"]

    @staticmethod
    def _default_sources(config: ResearchConfig) -> list[SearchSource]:
        """Construye las fuentes por defecto del proyecto con sus claves desde la config.

        Las claves de API son opcionales: una fuente sin su clave simplemente no se incluye
        (no está operativa) en lugar de hacer fallar la construcción. BDNS y TED son fuentes
        oficiales públicas (sin clave) y siempre están disponibles. Import perezoso de cada
        adaptador para no acoplar la fachada a sus SDKs cuando se inyectan fuentes propias.
        """
        from datetime import datetime

        from agente_ong.research.sources.bdns import BdnsSource
        from agente_ong.research.sources.firecrawl import FirecrawlSource
        from agente_ong.research.sources.tavily import TavilySource
        from agente_ong.research.sources.ted import TedSource

        sources: list[SearchSource] = []
        if config.tavily_api_key:
            sources.append(TavilySource(config))
        if config.firecrawl_api_key:
            sources.append(FirecrawlSource(config))
        # Fuentes oficiales públicas: siempre disponibles. `config.min_year` (R10) gobierna
        # el filtro temporal de ambas; sin él, BDNS no filtra y TED limita a los últimos
        # 2 años (año actual y anterior) para no traer licitaciones caducadas.
        sources.append(BdnsSource(config, min_year=config.min_year))
        sources.append(TedSource(config, min_year=config.min_year or (datetime.now().year - 1)))
        return sources
