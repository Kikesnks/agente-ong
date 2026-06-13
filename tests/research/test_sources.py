"""Tests de las fuentes con cliente/HTTP mockeado (sin red real).

Cubre el mapeo a SearchHit/FetchedDocument, el `is_official` correcto de cada fuente, y el
retry/backoff del helper común. _Requirements: 1.1, 6.1, NFR Reliability_
"""

from types import SimpleNamespace as NS

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import SearchQuery
from agente_ong.research.sources.base import with_retry
from agente_ong.research.sources.bdns import BdnsSource
from agente_ong.research.sources.firecrawl import FirecrawlSource
from agente_ong.research.sources.tavily import TavilySource
from agente_ong.research.sources.ted import TedSource


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Neutraliza las esperas del retry para que los tests no duerman."""
    monkeypatch.setattr("agente_ong.research.sources.base.time.sleep", lambda _s: None)


# --- Fakes de cliente ---


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeHttp:
    """Cliente HTTP falso que sirve `data` por GET o POST y registra las llamadas."""

    def __init__(self, data):
        self._data = data
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _FakeResponse(self._data)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _FakeResponse(self._data)


# --- with_retry (NFR Reliability) ---


def test_with_retry_returns_on_first_success():
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return "ok"

    assert with_retry(ok, sleep=lambda _s: None) == "ok"
    assert calls["n"] == 1


def test_with_retry_succeeds_after_failures_with_exponential_backoff():
    slept = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transitorio")
        return "ok"

    result = with_retry(
        flaky, attempts=3, base_delay=1.0, exceptions=(ValueError,), sleep=slept.append
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert slept == [1.0, 2.0]  # backoff exponencial


def test_with_retry_reraises_after_exhausting_attempts():
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise KeyError("siempre")

    with pytest.raises(KeyError):
        with_retry(always_fail, attempts=2, exceptions=(KeyError,), sleep=lambda _s: None)
    assert calls["n"] == 2


def test_with_retry_does_not_catch_unlisted_exceptions():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise TypeError("no listada")

    with pytest.raises(TypeError):
        with_retry(boom, exceptions=(ValueError,), sleep=lambda _s: None)
    assert calls["n"] == 1  # no reintenta una excepción no listada


# --- TavilySource (no oficial, search) ---


def test_tavily_maps_results_and_discards_without_url():
    client = _FakeHttp(None)  # placeholder; usamos cliente propio abajo

    class FakeTavily:
        def __init__(self):
            self.calls = []

        def search(self, query, **kw):
            self.calls.append((query, kw))
            return {
                "results": [
                    {"url": "https://a.es/x", "title": "A", "content": "snippet A"},
                    {"title": "sin url", "content": "descartar"},
                    {"url": "https://b.es/y", "title": "B", "content": "snippet B"},
                ]
            }

    fake = FakeTavily()
    src = TavilySource(ResearchConfig(tavily_api_key="k"), client=fake, max_results=7)
    hits = src.search(SearchQuery(text="cultura"))

    assert [h.url for h in hits] == ["https://a.es/x", "https://b.es/y"]
    assert all(h.source_name == "tavily" and h.is_official is False for h in hits)
    assert hits[0].snippet == "snippet A"
    assert fake.calls[0][1] == {"search_depth": "advanced", "max_results": 7}


def test_tavily_enriches_query_with_search_context():
    class FakeTavily:
        def __init__(self):
            self.calls = []

        def search(self, query, **kw):
            self.calls.append(query)
            return {"results": []}

    fake = FakeTavily()
    src = TavilySource(ResearchConfig(tavily_api_key="k"), client=fake)

    # Con search_context: se antepone al texto; el vocabulario de convocatoria (R16) se
    # añade SIEMPRE al final (complementa el contexto, no lo sustituye — 16.3).
    src.search(SearchQuery(text="agua", search_context="convocatoria subvención ONG 2026"))
    # Sin search_context: términos + vocabulario.
    src.search(SearchQuery(text="agua"))

    assert fake.calls[0].startswith("convocatoria subvención ONG 2026 agua")
    assert fake.calls[1].startswith("agua")
    vocabulario = " ".join(ResearchConfig().call_vocabulary)
    assert fake.calls[0].endswith(vocabulario)
    assert fake.calls[1].endswith(vocabulario)


def test_tavily_retries_then_succeeds():
    class Flaky:
        def __init__(self):
            self.n = 0

        def search(self, query, **kw):
            self.n += 1
            if self.n < 3:
                raise ConnectionError("net")
            return {"results": [{"url": "https://ok.es", "title": "ok", "content": "c"}]}

    flaky = Flaky()
    src = TavilySource(ResearchConfig(), client=flaky, retry_exceptions=(ConnectionError,))
    hits = src.search(SearchQuery(text="x"))
    assert flaky.n == 3 and hits[0].url == "https://ok.es"


# --- FirecrawlSource (no oficial, fetch) ---


def _fake_firecrawl_doc():
    return NS(
        markdown="# Convocatoria\nTexto",
        summary=None,
        links=["https://x.es/bases", "https://x.es/anexo"],
        metadata=NS(
            title="Conv X",
            source_url="https://x.es/conv",
            url=None,
            content_type="text/html",
            status_code=200,
        ),
    )


class _FakeFirecrawl:
    def __init__(self, doc):
        self.doc = doc
        self.calls = []

    def scrape(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.doc


def test_firecrawl_maps_document():
    fake = _FakeFirecrawl(_fake_firecrawl_doc())
    src = FirecrawlSource(ResearchConfig(firecrawl_api_key="k"), client=fake)
    doc = src.fetch("https://x.es/conv?utm=1")

    assert doc.url == "https://x.es/conv"  # source_url de metadata
    assert doc.title == "Conv X"
    assert doc.content_text.startswith("# Convocatoria")
    assert doc.content_type == "text/html"
    assert doc.raw_bytes is None  # Firecrawl no devuelve binario
    assert doc.outbound_links == ["https://x.es/bases", "https://x.es/anexo"]
    assert fake.calls[0][1] == {"formats": ["markdown", "links"], "only_main_content": True}


def test_firecrawl_handles_missing_metadata():
    doc = NS(markdown=None, summary=None, links=None, metadata=None)
    src = FirecrawlSource(ResearchConfig(), client=_FakeFirecrawl(doc))
    result = src.fetch("https://y.es/p")
    assert result.url == "https://y.es/p"  # fallback a la URL solicitada
    assert result.content_text == ""
    assert result.outbound_links == []


def test_firecrawl_does_not_retry_itself():
    # Firecrawl v4 ya reintenta internamente: la fuente NO envuelve con with_retry, así que
    # un error se propaga a la primera (call count == 1).
    class FailingClient:
        def __init__(self):
            self.n = 0

        def scrape(self, url, **kwargs):
            self.n += 1
            raise ConnectionError("boom")

    failing = FailingClient()
    src = FirecrawlSource(ResearchConfig(), client=failing)
    with pytest.raises(ConnectionError):
        src.fetch("https://x.es")
    assert failing.n == 1


# --- BdnsSource (oficial, search) ---


def test_bdns_maps_content_and_is_official():
    data = {
        "content": [
            {
                "numeroConvocatoria": "910123",
                "descripcion": "Ayudas cultura",
                "fechaRecepcion": "2026-06-02",
                "nivel1": "ESTADO",
                "nivel2": "MIN. CULTURA",
                "nivel3": None,
            },
            {"numeroConvocatoria": None, "descripcion": "descartar"},
        ]
    }
    http = _FakeHttp(data)
    src = BdnsSource(ResearchConfig(), client=http, max_results=15)
    hits = src.search(SearchQuery(text="cultura"))

    assert len(hits) == 1
    hit = hits[0]
    assert hit.url == "https://www.subvenciones.gob.es/bdnstrans/GE/es/convocatoria/910123"
    assert hit.title == "Ayudas cultura"
    assert hit.is_official is True and hit.source_name == "bdns"
    assert hit.snippet == "ESTADO / MIN. CULTURA (recepción: 2026-06-02)"
    assert http.calls[0][2]["params"] == {"descripcion": "cultura", "pageSize": 15, "page": 0}


@pytest.mark.parametrize("data", [{"content": []}, None, {}])
def test_bdns_empty_responses(data):
    src = BdnsSource(ResearchConfig(), client=_FakeHttp(data))
    assert src.search(SearchQuery(text="x")) == []


def test_bdns_retries_then_succeeds():
    class Flaky:
        def __init__(self):
            self.n = 0

        def get(self, url, **kw):
            self.n += 1
            if self.n < 3:
                raise ConnectionError("net")
            return _FakeResponse({"content": [{"numeroConvocatoria": "1", "descripcion": "x"}]})

    flaky = Flaky()
    src = BdnsSource(ResearchConfig(), client=flaky, retry_exceptions=(ConnectionError,))
    hits = src.search(SearchQuery(text="x"))
    assert flaky.n == 3 and len(hits) == 1


# --- BdnsSource: filtro temporal min_year (Requirements 10.2, 10.3) ---

# fechaRecepcion en ISO YYYY-MM-DD (formato real reverificado en vivo el 2026-06-10).
_BDNS_MIXED_YEARS = {
    "content": [
        {"numeroConvocatoria": "1", "descripcion": "antigua", "fechaRecepcion": "2023-11-30"},
        {"numeroConvocatoria": "2", "descripcion": "reciente", "fechaRecepcion": "2025-03-15"},
        {"numeroConvocatoria": "3", "descripcion": "sin fecha"},
    ]
}


def test_bdns_min_year_discards_older_calls():
    src = BdnsSource(ResearchConfig(), client=_FakeHttp(_BDNS_MIXED_YEARS), min_year=2025)
    titles = [h.title for h in src.search(SearchQuery(text="x"))]
    assert "antigua" not in titles
    assert "reciente" in titles


def test_bdns_min_year_keeps_calls_at_or_above_threshold():
    data = {
        "content": [
            {"numeroConvocatoria": "1", "descripcion": "del año", "fechaRecepcion": "2025-01-01"},
            {"numeroConvocatoria": "2", "descripcion": "posterior", "fechaRecepcion": "2026-06-09"},
        ]
    }
    src = BdnsSource(ResearchConfig(), client=_FakeHttp(data), min_year=2025)
    assert [h.title for h in src.search(SearchQuery(text="x"))] == ["del año", "posterior"]


def test_bdns_min_year_keeps_calls_without_parseable_date():
    # Sin fecha (o no parseable) NO se descarta: no se inventa antigüedad (Requirement 10.3).
    data = {
        "content": [
            {"numeroConvocatoria": "1", "descripcion": "sin fecha"},
            {"numeroConvocatoria": "2", "descripcion": "fecha rara", "fechaRecepcion": "??"},
        ]
    }
    src = BdnsSource(ResearchConfig(), client=_FakeHttp(data), min_year=2025)
    assert [h.title for h in src.search(SearchQuery(text="x"))] == ["sin fecha", "fecha rara"]


def test_bdns_min_year_none_does_not_filter():
    src = BdnsSource(ResearchConfig(), client=_FakeHttp(_BDNS_MIXED_YEARS))
    assert len(src.search(SearchQuery(text="x"))) == 3


# --- TedSource (oficial, search, POST) ---


def test_ted_maps_notices_with_multilingual_title_and_value():
    data = {
        "notices": [
            {
                "publication-number": "186818-2016",
                "TI": {"hun": "cim", "eng": "Cultural buildings"},
                "PD": "2016-06-02+02:00",
                "CY": ["DEU"],
                "buyer-name": {"eng": ["City of Duisburg"]},
                "total-value": 200000,
                "total-value-cur": ["GBP"],
            },
            {
                "publication-number": "999-2026",
                "TI": {"fra": "Bibliotheque"},
                "PD": "2026-01-01+01:00",
                "CY": ["FRA"],
                "estimated-value-proc": 3527457,
                "estimated-value-cur-proc": ["EUR"],
                "total-value": 10,
                "total-value-cur": ["EUR"],
            },
            {"ND": None, "TI": {"eng": "descartar"}},
        ]
    }
    http = _FakeHttp(data)
    src = TedSource(ResearchConfig(), client=http, max_results=12)
    hits = src.search(SearchQuery(text='cultural "library"'))

    assert len(hits) == 2  # el tercero sin publication-number/ND se descarta
    assert hits[0].url == "https://ted.europa.eu/en/notice/186818-2016"
    assert hits[0].title == "Cultural buildings"  # eng preferido sobre hun
    assert all(h.is_official is True and h.source_name == "ted" for h in hits)
    assert hits[0].snippet == "City of Duisburg | DEU | 2016-06-02 | valor total: 200000 GBP"
    # valor estimado preferido sobre total; título fallback a fra
    assert hits[1].title == "Bibliotheque"
    assert hits[1].snippet == "FRA | 2026-01-01 | valor estimado: 3527457 EUR"
    # query expert (comillas neutralizadas + strip) y POST
    body = http.calls[0][2]["json"]
    assert http.calls[0][0] == "POST"
    assert body["query"] == 'FT ~ "cultural  library"'
    assert body["page"] == 1 and body["limit"] == 12


def test_ted_omits_value_when_absent():
    data = {
        "notices": [
            {
                "publication-number": "1-2026",
                "TI": {"eng": "X"},
                "CY": ["ESP"],
                "PD": "2026-03-03+01:00",
            }
        ]
    }
    src = TedSource(ResearchConfig(), client=_FakeHttp(data))
    hits = src.search(SearchQuery(text="x"))
    assert hits[0].snippet == "ESP | 2026-03-03"  # sin importe inventado


def test_ted_appends_min_year_date_filter_to_query():
    # Con min_year se añade el filtro PD >= YYYYMMDD; sin él (default), no.
    http = _FakeHttp({"notices": []})
    src = TedSource(ResearchConfig(), client=http, min_year=2025)
    src.search(SearchQuery(text='cultural "library"'))

    body = http.calls[0][2]["json"]
    assert body["query"] == 'FT ~ "cultural  library" AND PD >= 20250101'


def test_ted_without_min_year_has_no_date_filter():
    http = _FakeHttp({"notices": []})
    src = TedSource(ResearchConfig(), client=http)  # min_year por defecto None
    src.search(SearchQuery(text="x"))

    assert http.calls[0][2]["json"]["query"] == 'FT ~ "x"'


def test_ted_retries_then_succeeds():
    class Flaky:
        def __init__(self):
            self.n = 0

        def post(self, url, **kw):
            self.n += 1
            if self.n < 3:
                raise ConnectionError("429")
            return _FakeResponse({"notices": [{"publication-number": "1", "TI": {"eng": "x"}}]})

    flaky = Flaky()
    src = TedSource(ResearchConfig(), client=flaky, retry_exceptions=(ConnectionError,))
    hits = src.search(SearchQuery(text="x"))
    assert flaky.n == 3 and len(hits) == 1


# --- is_official de cada fuente (Requirement 4.4 / verificación cruzada) ---


def test_official_flags():
    cfg = ResearchConfig()
    assert TavilySource(cfg, client=object()).is_official is False
    assert FirecrawlSource(cfg, client=object()).is_official is False
    assert BdnsSource(cfg, client=object()).is_official is True
    assert TedSource(cfg, client=object()).is_official is True
