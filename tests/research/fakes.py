"""Dobles de prueba compartidos para los tests de integración del agente investigador.

Provee fuentes fake (búsqueda y lectura) configurables, sin red ni SDKs, y pequeños builders
de modelos. La persistencia en integración usa los stores reales (`InMemoryStore` para casos
efímeros, `SqliteStore` con `tmp_path` para validar como lo verá el cliente).

Nota sobre el patrón: `SearchSource` declara `name`/`is_official`/`capabilities` como
propiedades abstractas; las fuentes fake las satisfacen con atributos de CLASE y luego las
sobrescriben por instancia en `__init__` para poder configurarlas por test.
"""

from __future__ import annotations

from agente_ong.research.models import FetchedDocument, SearchHit
from agente_ong.research.sources.base import SearchSource

# Re-exportado por conveniencia: la persistencia efímera de integración usa este store.
from agente_ong.research.store.memory import InMemoryStore  # noqa: F401


class FakeSearchSource(SearchSource):
    """Fuente de búsqueda fake: devuelve hits fijos; opcionalmente falla."""

    name = "fake-search"
    is_official = False
    capabilities = frozenset({"search"})

    def __init__(
        self,
        *,
        name: str = "fake-search",
        is_official: bool = False,
        hits: list[SearchHit] | None = None,
        fail: BaseException | type[BaseException] | None = None,
    ) -> None:
        self.name = name
        self.is_official = is_official
        self._hits = list(hits or [])
        self._fail = fail
        self.search_calls: list[str] = []

    def search(self, query):
        self.search_calls.append(query.text)
        _maybe_raise(self._fail)
        return list(self._hits)


class FakeFetchSource(SearchSource):
    """Fuente de lectura fake: devuelve documentos por URL; opcionalmente falla."""

    name = "fake-fetch"
    is_official = False
    capabilities = frozenset({"fetch"})

    def __init__(
        self,
        *,
        name: str = "fake-fetch",
        is_official: bool = False,
        documents: dict[str, FetchedDocument] | None = None,
        default_text: str = "contenido de la página",
        fail: BaseException | type[BaseException] | None = None,
    ) -> None:
        self.name = name
        self.is_official = is_official
        self._documents = dict(documents or {})
        self._default_text = default_text
        self._fail = fail
        self.fetch_calls: list[str] = []

    def fetch(self, url: str) -> FetchedDocument:
        self.fetch_calls.append(url)
        _maybe_raise(self._fail)
        if url in self._documents:
            return self._documents[url]
        return FetchedDocument(url=url, content_text=self._default_text, outbound_links=[])


def _maybe_raise(fail: BaseException | type[BaseException] | None) -> None:
    if fail is None:
        return
    raise fail if isinstance(fail, BaseException) else fail()


# --- Builders de modelos (reducen ruido en los tests) ---


def make_hit(
    url: str,
    *,
    source_name: str = "fake",
    title: str | None = None,
    snippet: str | None = None,
    is_official: bool = False,
) -> SearchHit:
    return SearchHit(
        url=url,
        source_name=source_name,
        title=title,
        snippet=snippet,
        is_official=is_official,
    )


def make_document(
    url: str,
    *,
    text: str = "contenido",
    title: str | None = None,
    links: list[str] | None = None,
    raw_bytes: bytes | None = None,
    content_type: str | None = None,
) -> FetchedDocument:
    return FetchedDocument(
        url=url,
        content_text=text,
        title=title,
        raw_bytes=raw_bytes,
        content_type=content_type,
        outbound_links=list(links or []),
    )
