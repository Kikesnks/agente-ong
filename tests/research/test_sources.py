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
from agente_ong.research.sources.reader import HttpReaderSource
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


def test_tavily_query_contains_call_vocabulary_term(monkeypatch):
    # R16.4: la query construida contiene al menos un término de vocabulario de convocatoria.
    class FakeTavily:
        def __init__(self):
            self.calls = []

        def search(self, query, **kw):
            self.calls.append(query)
            return {"results": []}

    fake = FakeTavily()
    TavilySource(ResearchConfig(tavily_api_key="k"), client=fake).search(
        SearchQuery(text="seguridad alimentaria")
    )
    assert any(term in fake.calls[0] for term in ResearchConfig().call_vocabulary)


def test_call_vocabulary_is_env_configurable(monkeypatch):
    monkeypatch.setenv("RESEARCH_CALL_VOCABULARY", "convocatoria abierta, financiación")
    config = ResearchConfig.from_env()
    assert config.call_vocabulary == ("convocatoria abierta", "financiación")

    monkeypatch.delenv("RESEARCH_CALL_VOCABULARY")
    from agente_ong.research.config import DEFAULT_CALL_VOCABULARY

    assert ResearchConfig.from_env().call_vocabulary == DEFAULT_CALL_VOCABULARY


def test_bdns_query_terms_are_not_altered_by_vocabulary():
    # R16.2: el corpus de BDNS ya es solo subvenciones; el término viaja tal cual.
    http = _FakeHttp({"content": []})
    BdnsSource(ResearchConfig(), client=http).search(SearchQuery(text="seguridad alimentaria"))
    assert http.calls[0][2]["params"]["descripcion"] == "seguridad alimentaria"


def _tavily_with_results(results, *, min_year=None):
    """TavilySource con un cliente fake que devuelve `results` fijos."""
    class FakeTavily:
        def search(self, query, **kw):
            return {"results": results}

    return TavilySource(
        ResearchConfig(tavily_api_key="k"), client=FakeTavily(), min_year=min_year
    )


# --- R17: filtro temporal de Tavily en cliente ---


def test_tavily_discards_old_published_date():
    src = _tavily_with_results(
        [
            {"url": "https://x.es/viejo", "title": "Estudio", "published_date": "2009-11-02"},
            {"url": "https://x.es/nuevo", "title": "Convocatoria", "published_date": "2026-01-10"},
        ],
        min_year=2025,
    )
    urls = [h.url for h in src.search(SearchQuery(text="agua"))]
    assert urls == ["https://x.es/nuevo"]


def test_tavily_discards_old_year_in_title():
    # Caso real del diagnóstico: "Crisis y pobreza rural... Noviembre 2009".
    src = _tavily_with_results(
        [
            {"url": "https://x.es/a", "title": "Crisis y pobreza rural. Noviembre 2009"},
            {"url": "https://x.es/b", "title": "Convocatoria 2026 de ayudas"},
        ],
        min_year=2025,
    )
    hits = src.search(SearchQuery(text="rural"))
    assert [h.url for h in hits] == ["https://x.es/b"]
    assert hits[0].published_year == 2026


def test_tavily_keeps_undated_results_with_published_year_none():
    # R17.2: sin fecha identificable NO se descarta; published_year queda en None.
    src = _tavily_with_results(
        [{"url": "https://x.es/sinfecha", "title": "Subvenciones para cultura"}],
        min_year=2025,
    )
    hits = src.search(SearchQuery(text="cultura"))
    assert len(hits) == 1 and hits[0].published_year is None


def test_tavily_year_only_in_body_does_not_discard():
    # Un año en el cuerpo no data el documento (solo título/published_date).
    src = _tavily_with_results(
        [{"url": "https://x.es/a", "title": "Ayudas vigentes", "content": "ejecutó fondos de 2009"}],
        min_year=2025,
    )
    hits = src.search(SearchQuery(text="ayudas"))
    assert len(hits) == 1 and hits[0].published_year is None


def test_tavily_min_year_none_does_not_filter():
    src = _tavily_with_results(
        [{"url": "https://x.es/a", "title": "Algo de 2009"}], min_year=None
    )
    assert len(src.search(SearchQuery(text="x"))) == 1


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


# --- R19: detalle de BDNS (importe y plazo) ---


class _RoutingHttp:
    """Cliente fake que enruta GET por path: búsqueda vs detalle, y cuenta cada uno."""

    def __init__(self, search_data, detail_by_num=None, *, detail_fails=False):
        self._search_data = search_data
        self._detail_by_num = detail_by_num or {}
        self._detail_fails = detail_fails
        self.search_calls = 0
        self.detail_calls = 0
        self.detail_nums: list[str] = []

    def get(self, url, **kw):
        if url.endswith("/busqueda"):
            self.search_calls += 1
            return _FakeResponse(self._search_data)
        # detalle
        self.detail_calls += 1
        num = str(kw.get("params", {}).get("numConv"))
        self.detail_nums.append(num)
        if self._detail_fails:
            raise ConnectionError("detalle caído")
        return _FakeResponse(self._detail_by_num.get(num, {}))


def _search_page(*numeros, fecha="2026-01-10"):
    return {
        "content": [
            {"numeroConvocatoria": n, "descripcion": f"Conv {n}", "fechaRecepcion": fecha}
            for n in numeros
        ]
    }


def test_bdns_detail_fills_amount_and_deadline():
    http = _RoutingHttp(
        _search_page("100"),
        {
            "100": {
                "presupuestoTotal": 307600,
                "fechaFinSolicitud": "2026-12-20",
                "abierto": True,
            }
        },
    )
    src = BdnsSource(ResearchConfig(), client=http)
    hit = src.search(SearchQuery(text="cultura"))[0]
    assert hit.amount == "307.600 €"
    assert hit.deadline == "hasta 2026-12-20 (abierto)"
    assert http.detail_calls == 1


def test_bdns_detail_call_limit_is_respected():
    http = _RoutingHttp(_search_page("1", "2", "3", "4", "5"))
    src = BdnsSource(ResearchConfig(), client=http, max_detail_calls=2)
    src.search(SearchQuery(text="x"))
    assert http.detail_calls == 2  # solo los 2 primeros, aunque haya 5 hits


def test_bdns_min_year_filters_before_detail_calls():
    # Dos convocatorias: una de 2023 (descartada por min_year) y una de 2026.
    data = {
        "content": [
            {"numeroConvocatoria": "viejo", "descripcion": "V", "fechaRecepcion": "2023-05-01"},
            {"numeroConvocatoria": "nuevo", "descripcion": "N", "fechaRecepcion": "2026-05-01"},
        ]
    }
    http = _RoutingHttp(data, {"nuevo": {"presupuestoTotal": 1000}})
    src = BdnsSource(ResearchConfig(), client=http, min_year=2025)
    hits = src.search(SearchQuery(text="x"))
    # Solo se pide el detalle de la superviviente (no se gastan llamadas en descartes).
    assert http.detail_calls == 1 and http.detail_nums == ["nuevo"]
    assert [h.title for h in hits] == ["N"]


def test_bdns_detail_failure_keeps_hit_without_amount_deadline():
    http = _RoutingHttp(_search_page("100"), detail_fails=True)
    src = BdnsSource(
        ResearchConfig(), client=http, retry_exceptions=(ConnectionError,)
    )
    hits = src.search(SearchQuery(text="x"))
    assert len(hits) == 1  # el fallo del detalle no descarta el hit
    assert hits[0].amount is None and hits[0].deadline is None


def test_bdns_detail_without_fields_leaves_none():
    http = _RoutingHttp(_search_page("100"), {"100": {"descripcion": "sin importe ni plazo"}})
    src = BdnsSource(ResearchConfig(), client=http)
    hit = src.search(SearchQuery(text="x"))[0]
    assert hit.amount is None and hit.deadline is None


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


# --- HttpReaderSource (no oficial, fetch, lector propio sin créditos — R23) ---


class _FakeHtmlResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self._status_code = status_code

    def raise_for_status(self):
        if self._status_code >= 400:
            raise RuntimeError(f"HTTP {self._status_code}")


class _FakeHtmlClient:
    """Cliente HTTP falso que devuelve `text`/`status_code` fijos por GET."""

    def __init__(self, text, status_code=200):
        self._text = text
        self._status_code = status_code
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeHtmlResponse(self._text, self._status_code)


# Página real con contenido útil y enlaces (forma representativa de una convocatoria).
_READER_PAGE_WITH_CONTENT = """<html><head><title>Convocatoria de ayudas</title></head>
<body>
<nav>Inicio | Skip to content | Aviso de cookies | ES / CAT / EN</nav>
<article>
<h1>Convocatoria de subvenciones 2026</h1>
<p>Esta es la convocatoria de subvenciones para proyectos de cooperacion internacional.
El plazo de presentacion de solicitudes finaliza el 30 de septiembre de 2026. Las bases
reguladoras detallan los requisitos de los beneficiarios y la dotacion presupuestaria
disponible para esta convocatoria de ayudas.</p>
<a href="/bases">Bases reguladoras</a>
<a href="https://otro.example/anexo">Anexo</a>
<a href="#top">Volver arriba</a>
</article>
<footer>Politica de privacidad | Aviso legal | Suscribete a nuestro boletin</footer>
</body></html>"""

# HTML real de una SPA (Angular) sin contenido server-side: trafilatura no extrae nada
# (capturado en la verificación en vivo de R23.6 contra una página de detalle de BDNS).
_READER_PAGE_SPA_SHELL = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Sistema Nacional de Publicidad de Subvenciones y Ayudas Publicas</title>
  <base href="/bdnstrans/">
  <link rel="stylesheet" href="styles.css">
</head>
<body class="background">
  <app-root></app-root>
  <script src="main.js" type="module"></script>
</body>
</html>"""


def test_reader_extracts_text_and_outbound_links():
    client = _FakeHtmlClient(_READER_PAGE_WITH_CONTENT)
    src = HttpReaderSource(ResearchConfig(), client=client)

    doc = src.fetch("https://x.example/conv")

    assert "convocatoria de subvenciones" in doc.content_text.lower()
    assert "plazo de presentacion" in doc.content_text.lower()
    # Plantilla web (cookies/nav/footer) descartada por trafilatura.
    assert "aviso de cookies" not in doc.content_text.lower()
    assert "politica de privacidad" not in doc.content_text.lower()
    assert doc.title == "Convocatoria de ayudas"
    assert doc.content_type == "text/html"
    assert doc.raw_bytes is None
    # Enlaces absolutos http(s), sin fragmentos, deduplicados.
    assert doc.outbound_links == ["https://x.example/bases", "https://otro.example/anexo"]


def test_reader_caps_outbound_links_at_50():
    links_html = "".join(f'<a href="https://x.example/p{i}">p{i}</a>' for i in range(80))
    html = f"<html><body><article>{_READER_PAGE_WITH_CONTENT}{links_html}</article></body></html>"
    src = HttpReaderSource(ResearchConfig(), client=_FakeHtmlClient(html))

    doc = src.fetch("https://x.example/conv")

    assert len(doc.outbound_links) == 50


def test_reader_empty_extraction_is_failure():
    # HTML real (SPA sin contenido server-side): extracción vacía => fallo, no se inventa nada.
    src = HttpReaderSource(ResearchConfig(), client=_FakeHtmlClient(_READER_PAGE_SPA_SHELL))
    with pytest.raises(ValueError):
        src.fetch("https://www.subvenciones.gob.es/bdnstrans/GE/es/convocatoria/912840")


def test_reader_http_error_is_failure_without_extraction(monkeypatch):
    # Un 503 (p.ej. WAF) se descarta por raise_for_status ANTES de pasar por trafilatura,
    # aunque el cuerpo de error tenga texto.
    client = _FakeHtmlClient("Error 503 - Service Unavailable", status_code=503)
    src = HttpReaderSource(ResearchConfig(), client=client, retry_exceptions=(RuntimeError,))
    monkeypatch.setattr("agente_ong.research.sources.base.time.sleep", lambda _s: None)
    with pytest.raises(RuntimeError):
        src.fetch("https://bloqueado.example/conv")


def test_reader_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("agente_ong.research.sources.base.time.sleep", lambda _s: None)

    class Flaky:
        def __init__(self):
            self.n = 0

        def get(self, url, **kwargs):
            self.n += 1
            if self.n < 3:
                raise ConnectionError("red caída")
            return _FakeHtmlResponse(_READER_PAGE_WITH_CONTENT)

    flaky = Flaky()
    src = HttpReaderSource(ResearchConfig(), client=flaky, retry_exceptions=(ConnectionError,))
    doc = src.fetch("https://x.example/conv")

    assert flaky.n == 3
    assert "convocatoria de subvenciones" in doc.content_text.lower()


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
    # max_detail_calls=0 aísla el reintento de la BÚSQUEDA (sin llamadas al detalle R19).
    src = BdnsSource(
        ResearchConfig(), client=flaky, retry_exceptions=(ConnectionError,), max_detail_calls=0
    )
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
    assert HttpReaderSource(cfg, client=object()).is_official is False
    assert BdnsSource(cfg, client=object()).is_official is True
    assert TedSource(cfg, client=object()).is_official is True


def test_reader_name_and_capabilities():
    src = HttpReaderSource(ResearchConfig(), client=object())
    assert src.name == "reader"
    assert src.capabilities == frozenset({"fetch"})
    assert src.supports("fetch") is True
    assert src.supports("search") is False
