"""Fuente de lectura profunda vía Firecrawl.

`FirecrawlSource` implementa la capacidad `fetch`: lee una URL y devuelve su contenido en
texto (markdown) junto con sus enlaces salientes, que alimentan la profundización del agente
(seguir enlaces relevantes, Requirement 6.1). No es una fuente oficial.

Nota sobre reintentos: a diferencia de las demás fuentes, FirecrawlSource NO usa el helper
`with_retry`. El cliente de firecrawl-py v4 ya reintenta internamente con backoff propio
(parámetros `max_retries` y `backoff_factor` de `Firecrawl`), así que envolverlo de nuevo
duplicaría los reintentos. La red de seguridad ya está dentro del cliente.

`raw_bytes` es siempre None en esta fuente: Firecrawl devuelve texto/markdown, no binario. La
descarga del archivo binario original (PDFs, etc.) la realiza el `TrainingCollector`
(tarea 23) mediante HTTP directo, no este adaptador.
"""

from __future__ import annotations

from typing import Any, Protocol

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import FetchedDocument
from agente_ong.research.sources.base import Capability, SearchSource

# Backoff propio del cliente firecrawl-py v4 (ver nota del módulo).
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_FACTOR = 0.5


class _FirecrawlClient(Protocol):
    """Contrato mínimo que necesita FirecrawlSource (lo cumple firecrawl.Firecrawl)."""

    def scrape(self, url: str, **kwargs: Any) -> Any: ...


class FirecrawlSource(SearchSource):
    """Lectura profunda de páginas (no oficial) a través de Firecrawl."""

    name = "firecrawl"
    is_official = False
    capabilities: frozenset[Capability] = frozenset({"fetch"})
    # Fallback de configuración (R23): no aparece en el selector de fuentes de la UI, por
    # lo que `enabled_sources` no debe excluirlo.
    user_selectable = False

    def __init__(
        self,
        config: ResearchConfig,
        client: _FirecrawlClient | None = None,
    ) -> None:
        self._config = config
        if client is None:
            # Import perezoso: solo se necesita firecrawl si no se inyecta un cliente (tests).
            from firecrawl import Firecrawl

            client = Firecrawl(
                api_key=config.firecrawl_api_key,
                max_retries=_DEFAULT_MAX_RETRIES,
                backoff_factor=_DEFAULT_BACKOFF_FACTOR,
            )
        self._client = client

    def fetch(self, url: str) -> FetchedDocument:
        """Lee la URL y la mapea a `FetchedDocument` (texto + enlaces salientes).

        Sin `with_retry`: el cliente de firecrawl-py v4 ya reintenta internamente.
        """
        # Solo markdown (texto limpio) + links (para profundización). Sin html.
        doc = self._client.scrape(
            url,
            formats=["markdown", "links"],
            only_main_content=True,
        )
        return self._to_document(url, doc)

    def _to_document(self, requested_url: str, doc: Any) -> FetchedDocument:
        metadata = getattr(doc, "metadata", None)

        # url: preferimos la URL real reportada por la metadata; si no, la solicitada.
        resolved_url = (
            getattr(metadata, "source_url", None)
            or getattr(metadata, "url", None)
            or requested_url
        )

        content_text = getattr(doc, "markdown", None) or getattr(doc, "summary", None) or ""
        links = getattr(doc, "links", None) or []

        return FetchedDocument(
            url=resolved_url,
            content_text=content_text,
            title=getattr(metadata, "title", None),
            raw_bytes=None,  # Firecrawl no devuelve binario (ver nota del módulo).
            content_type=getattr(metadata, "content_type", None),
            outbound_links=list(links),
        )
