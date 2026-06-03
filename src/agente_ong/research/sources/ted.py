"""Fuente oficial de la UE: TED (Tenders Electronic Daily).

`TedSource` consulta TED, el diario de contratación pública de la Unión Europea, vía su API
v3 pública (acceso anónimo, sin clave). Es una fuente **oficial** (`is_official = True`).

Importante: TED cubre **contratos por encima de umbrales** (licitaciones grandes), no
subvenciones pequeñas. No es la fuente principal para ONGs; aporta cobertura europea como
complemento de BDNS.

Notas sobre la API real (verificadas con llamadas en vivo):
  - Búsqueda: POST https://api.ted.europa.eu/v3/notices/search (es POST, no GET).
  - El cuerpo lleva `query` en el "expert query language" de TED (no texto libre): el texto
    del usuario se envuelve como `FT ~ "<texto>"` (full-text).
  - `fields` es OBLIGATORIO y la API solo devuelve los campos solicitados.
  - Respuesta: { notices: [...], totalNoticeCount, iterationNextToken, timedOut }.
  - Cada notice: `publication-number`/`ND` (id, p.ej. "186818-2016"), `TI` (dict multilingüe
    por código ISO-3, p.ej. {"eng": "..."}), `PD` (fecha), `CY` (lista de países),
    `buyer-name` (dict multilingüe de listas), `links`.
  - Importe: `total-value` (adjudicado) + `total-value-cur` (lista de moneda), y/o
    `estimated-value-{proc,glo,lot}` (estimado) + sus `*-cur`.
  - URL pública del notice: https://ted.europa.eu/en/notice/{publication-number}
  - Tiene rate limits -> se usa with_retry.
"""

from __future__ import annotations

from typing import Any, Protocol

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import SearchHit, SearchQuery
from agente_ong.research.sources.base import Capability, SearchSource, with_retry

_API_URL = "https://api.ted.europa.eu/v3/notices/search"
_PUBLIC_NOTICE_URL = "https://ted.europa.eu/en/notice/{}"

# Idiomas preferidos para los campos multilingües (códigos ISO-639-3 de TED).
_PREFERRED_LANGS = ("eng", "fra", "spa", "deu")

# Campos a solicitar (la API solo devuelve lo que se pide).
_FIELDS = [
    "publication-number",
    "ND",
    "TI",
    "PD",
    "CY",
    "buyer-name",
    "links",
    # Importe: estimado (preferido para convocatorias abiertas) y total (adjudicado).
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "estimated-value-glo",
    "estimated-value-cur-glo",
    "estimated-value-lot",
    "estimated-value-cur-lot",
    "total-value",
    "total-value-cur",
]

# Pares (campo_importe, campo_moneda) en orden de preferencia: estimado antes que total.
_VALUE_FIELDS = [
    ("estimated-value-proc", "estimated-value-cur-proc", "valor estimado"),
    ("estimated-value-glo", "estimated-value-cur-glo", "valor estimado"),
    ("estimated-value-lot", "estimated-value-cur-lot", "valor estimado"),
    ("total-value", "total-value-cur", "valor total"),
]


class _HttpResponse(Protocol):
    def raise_for_status(self) -> Any: ...
    def json(self) -> Any: ...


class _HttpClient(Protocol):
    """Contrato mínimo de cliente HTTP con POST (lo cumple httpx.Client)."""

    def post(self, url: str, **kwargs: Any) -> _HttpResponse: ...


class TedSource(SearchSource):
    """Búsqueda de licitaciones en TED (fuente oficial de la UE)."""

    name = "ted"
    is_official = True
    capabilities: frozenset[Capability] = frozenset({"search"})

    def __init__(
        self,
        config: ResearchConfig,
        client: _HttpClient | None = None,
        *,
        max_results: int = 20,
        retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self._config = config  # nota: TED permite acceso anónimo, no usa ted_api_key
        self._max_results = max_results
        self._retry_exceptions = retry_exceptions
        if client is None:
            # Import perezoso: solo se necesita httpx si no se inyecta un cliente (tests).
            import httpx

            client = httpx.Client(timeout=40, headers={"Accept": "application/json"})
        self._client = client

    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Busca notices en TED y mapea el resultado eForms a `SearchHit`."""
        payload = {
            "query": self._expert_query(query.text),
            "limit": self._max_results,
            "page": 1,  # TED pagina desde 1
            "fields": _FIELDS,
        }

        def call() -> Any:
            response = self._client.post(_API_URL, json=payload)
            response.raise_for_status()
            return response.json()

        data = with_retry(call, exceptions=self._retry_exceptions)
        return self._to_hits(data)

    @staticmethod
    def _expert_query(text: str) -> str:
        # Envolver el texto libre como full-text del expert query; las comillas se neutralizan.
        safe = (text or "").replace('"', " ").strip()
        return f'FT ~ "{safe}"'

    def _to_hits(self, data: Any) -> list[SearchHit]:
        if not isinstance(data, dict):
            return []
        hits: list[SearchHit] = []
        for notice in data.get("notices") or []:
            pub = notice.get("publication-number") or notice.get("ND")
            if not pub:
                # Sin número de publicación no hay URL oficial: se descarta.
                continue
            hits.append(
                SearchHit(
                    url=_PUBLIC_NOTICE_URL.format(pub),
                    source_name=self.name,
                    title=_pick_lang(notice.get("TI")),
                    snippet=self._build_snippet(notice),
                    is_official=True,
                )
            )
        return hits

    def _build_snippet(self, notice: dict[str, Any]) -> str | None:
        parts: list[str] = []

        buyer = _pick_lang(notice.get("buyer-name"))
        if buyer:
            parts.append(buyer)

        countries = notice.get("CY")
        if isinstance(countries, list) and countries:
            parts.append(", ".join(str(c) for c in countries))
        elif isinstance(countries, str) and countries:
            parts.append(countries)

        date = notice.get("PD")
        if date:
            # PD viene como "2016-06-02+02:00"; nos quedamos con la fecha.
            parts.append(str(date)[:10])

        economic = self._economic(notice)
        if economic:
            parts.append(economic)

        return " | ".join(parts) or None

    @staticmethod
    def _economic(notice: dict[str, Any]) -> str | None:
        """Importe disponible (estimado preferido sobre total). No inventa nada."""
        for value_field, cur_field, label in _VALUE_FIELDS:
            amount = notice.get(value_field)
            if amount in (None, "", 0):
                continue
            currency = notice.get(cur_field)
            if isinstance(currency, list) and currency:
                currency = currency[0]
            return f"{label}: {amount} {currency}".strip() if currency else f"{label}: {amount}"
        return None


def _pick_lang(value: Any) -> str | None:
    """Extrae un texto de un campo multilingüe TED ({lang: str | [str]}).

    Prioriza los idiomas de `_PREFERRED_LANGS`; si no, toma cualquier idioma disponible.
    Acepta valores que sean cadena o lista de cadenas.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if not isinstance(value, dict) or not value:
        return None

    keys = list(_PREFERRED_LANGS) + [k for k in value if k not in _PREFERRED_LANGS]
    for lang in keys:
        if lang not in value:
            continue
        item = value[lang]
        if isinstance(item, list):
            if item:
                return str(item[0])
        elif item:
            return str(item)
    return None
