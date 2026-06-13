"""Fuente de búsqueda general vía Tavily.

`TavilySource` implementa la capacidad `search` contra la API de Tavily. No es una fuente
oficial (`is_official = False`): sus resultados deben cruzarse con otras fuentes (ver política
de verificación). El cliente es inyectable, lo que permite testear sin red y sustituir el
backend sin tocar la lógica (Requirement 7.2/7.3).
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import SearchHit, SearchQuery
from agente_ong.research.sources.base import Capability, SearchSource, with_retry

# Año plausible (1900-2099) para datar un resultado a partir de su título o published_date.
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


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
        min_year: int | None = None,
        retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self._config = config
        self._max_results = max_results
        # "advanced" prioriza calidad de resultados sobre velocidad (principio de producto).
        self._search_depth = search_depth
        # Filtro temporal en cliente (R17); None = sin filtro. Se aplica por año
        # identificado en published_date o, en su defecto, en el TÍTULO.
        self._min_year = min_year
        self._retry_exceptions = retry_exceptions
        if client is None:
            # Import perezoso: solo se necesita tavily si no se inyecta un cliente (tests).
            from tavily import TavilyClient

            client = TavilyClient(api_key=config.tavily_api_key)
        self._client = client

    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Lanza la búsqueda y mapea los resultados de Tavily a `SearchHit`.

        La query se compone como "{contexto} {términos} {vocabulario}" (R16): el
        `search_context` del proyecto se mantiene delante (se complementa, no se
        sustituye) y el vocabulario de convocatoria orienta el ranking hacia la OFERTA de
        financiación, no hacia proyectos ya financiados o noticias.
        """
        parts = [query.search_context, query.text, " ".join(self._config.call_vocabulary)]
        text = " ".join(p for p in parts if p)

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
            year = self._identify_year(result)
            # R17.1: con fecha identificada anterior a min_year, se descarta. R17.2: sin
            # fecha identificable NO se descarta (no inventar antigüedad).
            if self._min_year is not None and year is not None and year < self._min_year:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    source_name=self.name,
                    title=result.get("title"),
                    snippet=result.get("content"),
                    is_official=False,
                    published_year=year,
                )
            )
        return hits

    @staticmethod
    def _identify_year(result: dict[str, Any]) -> int | None:
        """Año del resultado: de `published_date` si viene, si no del TÍTULO.

        El cuerpo/snippet NO se usa: citar un año dentro del texto no data el documento
        (un resultado actual puede mencionar "los fondos de 2009"). Verificado en vivo el
        13-06-2026: con topic='general' Tavily no devuelve `published_date`, así que en la
        práctica el año casi siempre sale del título (caso real: "… Noviembre 2009").
        """
        published = result.get("published_date")
        if isinstance(published, str):
            match = _YEAR_RE.search(published)
            if match:
                return int(match.group(0))
        title = result.get("title")
        if isinstance(title, str):
            match = _YEAR_RE.search(title)
            if match:
                return int(match.group(0))
        return None
