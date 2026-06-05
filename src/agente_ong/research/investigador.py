"""Fachada pública del agente investigador.

`Investigador` es el único punto de entrada del módulo y su superficie portable: se construye
con una `ResearchConfig` (y, opcionalmente, fuentes y store inyectados) y expone
`run(request) -> ResearchReport`. Internamente arma la capa de fuentes, el ledger, la política
de verificación, el limitador de profundidad y el collector, y ejecuta el grafo LangGraph.

Portabilidad (Requirement 7): el núcleo no depende de la UI ni de ENGRAM. Por defecto usa
`InMemoryStore` (portátil); en agente-ong se le inyecta `EngramStore` para recall entre
sesiones. Las fuentes por defecto se construyen con sus claves desde la config (Requirement
7.2); se pueden sustituir inyectando otras (Requirement 7.3).

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
        self._store = store if store is not None else InMemoryStore()
        self._sources = sources if sources is not None else self._default_sources(config)
        # Colaboradores sin estado por investigación (se pueden compartir entre runs).
        self._policy = VerificationPolicy(config)
        self._limiter = DepthLimiter(config)
        self._collector = TrainingCollector(config, self._store)

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
        from agente_ong.research.sources.bdns import BdnsSource
        from agente_ong.research.sources.firecrawl import FirecrawlSource
        from agente_ong.research.sources.tavily import TavilySource
        from agente_ong.research.sources.ted import TedSource

        sources: list[SearchSource] = []
        if config.tavily_api_key:
            sources.append(TavilySource(config))
        if config.firecrawl_api_key:
            sources.append(FirecrawlSource(config))
        # Fuentes oficiales públicas: siempre disponibles.
        sources.append(BdnsSource(config))
        sources.append(TedSource(config))
        return sources
