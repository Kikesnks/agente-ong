"""Lectura profunda propia vía httpx + trafilatura, sin dependencia de créditos (R23).

`HttpReaderSource` implementa la capacidad `fetch` (mismo puerto que `FirecrawlSource`,
R23.1): descarga la página con `httpx` y extrae su texto principal con `trafilatura`,
que ya descarta plantilla web (menús, cookies, footers) en origen — `textclean` (R18) sigue
aplicándose después, complementa, no sustituye.

`trafilatura` no devuelve enlaces salientes: se extraen del HTML con `lxml` (solo `<a href>`
absolutos http(s), sin fragmento, deduplicados y acotados a `_MAX_OUTBOUND_LINKS`) para
alimentar la profundización (`read_deep`) como hacía Firecrawl.

A diferencia de `firecrawl-py`, `httpx` no reintenta solo: se envuelve con `with_retry`
(NFR Reliability). Una extracción vacía (p.ej. páginas SPA sin contenido server-side, como
algunas de BDNS) se trata como fallo: dispara el fallback configurado (R23.2).

Verificación en vivo (R23.6, 12-06-2026): una página BOE normal extrae texto limpio con
`trafilatura.extract()`; una página BDNS (Angular SPA) devuelve un HTML mínimo sin
contenido y `extract()` devuelve `None` (fallo, correcto); una página bloqueada por WAF
(503) se descarta por `raise_for_status()` antes de llegar a `trafilatura` (nunca se trata
un error HTTP como contenido). Los enlaces salientes se obtienen con
`tree.iterlinks()` filtrando `tag == "a"` (incluir todos los elementos con atributos de
enlace —css, favicons, scripts— sería ruido).
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urldefrag

import trafilatura
from lxml import html as lxml_html

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import FetchedDocument
from agente_ong.research.sources.base import Capability, SearchSource, with_retry

_DEFAULT_TIMEOUT = 30
# User-Agent de navegador: algunos sitios bloquean clientes sin él (p.ej. WAFs).
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_MAX_OUTBOUND_LINKS = 50


class _HttpResponse(Protocol):
    def raise_for_status(self) -> Any: ...

    @property
    def text(self) -> str: ...


class _HttpClient(Protocol):
    """Contrato mínimo que necesita HttpReaderSource (lo cumple httpx.Client)."""

    def get(self, url: str, **kwargs: Any) -> _HttpResponse: ...


class HttpReaderSource(SearchSource):
    """Lectura profunda de páginas (no oficial) vía httpx + trafilatura, sin coste."""

    name = "reader"
    is_official = False
    capabilities: frozenset[Capability] = frozenset({"fetch"})

    def __init__(
        self,
        config: ResearchConfig,
        client: _HttpClient | None = None,
        *,
        retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self._config = config
        self._retry_exceptions = retry_exceptions
        if client is None:
            # Import perezoso: solo se necesita httpx si no se inyecta un cliente (tests).
            import httpx

            client = httpx.Client(
                timeout=_DEFAULT_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _DEFAULT_USER_AGENT},
            )
        self._client = client

    def fetch(self, url: str) -> FetchedDocument:
        """Descarga `url` y extrae su texto principal y enlaces salientes.

        Una extracción vacía (HTML sin contenido recuperable, p.ej. una SPA) se trata como
        fallo (`ValueError`): el llamador (`read_deep`) lo registra y, si procede, recurre
        al fallback (R23.2/23.5).
        """

        def call() -> str:
            response = self._client.get(url)
            response.raise_for_status()
            return response.text

        html = with_retry(call, exceptions=self._retry_exceptions)
        text = trafilatura.extract(html, url=url)
        if not text:
            raise ValueError(f"El lector propio no extrajo contenido de {url}")

        return FetchedDocument(
            url=url,
            content_text=text,
            title=_extract_title(html),
            raw_bytes=None,  # el lector propio solo procesa HTML, nunca binario.
            content_type="text/html",
            outbound_links=_extract_links(html, url),
        )


def _extract_title(html: str) -> str | None:
    try:
        tree = lxml_html.fromstring(html)
    except Exception:  # noqa: BLE001 - un HTML inválido no debe romper el fetch
        return None
    title = tree.findtext(".//head/title")
    return title.strip() if title and title.strip() else None


def _extract_links(html: str, base_url: str) -> list[str]:
    """Enlaces salientes absolutos http(s) de los `<a href>` del documento (R23.1)."""
    try:
        tree = lxml_html.fromstring(html)
        tree.make_links_absolute(base_url)
    except Exception:  # noqa: BLE001 - un HTML inválido se trata como sin enlaces
        return []

    base, _fragment = urldefrag(base_url)
    links: list[str] = []
    seen: set[str] = {base}
    for element, attribute, link, _pos in tree.iterlinks():
        if element.tag != "a" or attribute != "href":
            continue
        clean, _fragment = urldefrag(link)
        if clean.startswith(("http://", "https://")) and clean not in seen:
            seen.add(clean)
            links.append(clean)
            if len(links) >= _MAX_OUTBOUND_LINKS:
                break
    return links
