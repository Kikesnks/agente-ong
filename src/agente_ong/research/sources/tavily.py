"""Fuente de búsqueda general vía Tavily.

`TavilySource` implementa la capacidad `search` contra la API de Tavily. No es una fuente
oficial (`is_official = False`): sus resultados deben cruzarse con otras fuentes (ver política
de verificación). El cliente es inyectable, lo que permite testear sin red y sustituir el
backend sin tocar la lógica (Requirement 7.2/7.3).
"""

from __future__ import annotations

from typing import Any, Protocol

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import SearchHit, SearchQuery
from agente_ong.research.sources.base import Capability, SearchSource, with_retry


class _TavilyClient(Protocol):
    """Contrato mínimo que necesita TavilySource (lo cumple tavily.TavilyClient)."""

    def search(self, query: str, **kwargs: Any) -> dict[str, Any]: ...


class TavilySource(SearchSource):
    """Búsqueda web general (no oficial) a través de Tavily."""

    name = "tavily"
    is_official = False
    capabilities: frozenset[Capability] = frozenset({"search"})

    def __init__(
        self,
        config: ResearchConfig,
        client: _TavilyClient | None = None,
        *,
        max_results: int = 10,
        search_depth: str = "advanced",
        retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self._config = config
        self._max_results = max_results
        # "advanced" prioriza calidad de resultados sobre velocidad (principio de producto).
        self._search_depth = search_depth
        self._retry_exceptions = retry_exceptions
        if client is None:
            # Import perezoso: solo se necesita tavily si no se inyecta un cliente (tests).
            from tavily import TavilyClient

            client = TavilyClient(api_key=config.tavily_api_key)
        self._client = client

    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Lanza la búsqueda y mapea los resultados de Tavily a `SearchHit`.

        Si la query trae `search_context`, lo antepone al texto para orientar la búsqueda
        (p.ej. "convocatoria subvención ONG 2026"); si no, usa el texto tal cual.
        """
        text = f"{query.search_context} {query.text}" if query.search_context else query.text

        def call() -> dict[str, Any]:
            return self._client.search(
                text,
                search_depth=self._search_depth,
                max_results=self._max_results,
            )

        raw = with_retry(call, exceptions=self._retry_exceptions)
        return self._to_hits(raw)

    def _to_hits(self, raw: dict[str, Any]) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for result in raw.get("results", []):
            url = result.get("url")
            if not url:
                # Sin URL no hay procedencia verificable: se descarta el resultado.
                continue
            hits.append(
                SearchHit(
                    url=url,
                    source_name=self.name,
                    title=result.get("title"),
                    snippet=result.get("content"),
                    is_official=False,
                )
            )
        return hits
