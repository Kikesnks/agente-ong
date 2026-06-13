"""Fuente oficial de convocatorias de España: BDNS.

`BdnsSource` consulta la Base de Datos Nacional de Subvenciones (BDNS) del Gobierno de España
a través de su API pública (sin autenticación ni clave). Es una fuente **oficial**
(`is_official = True`): sus datos se consideran fiables sin verificación cruzada, aunque se
marquen como "fuente oficial, no cruzada" (ver política de verificación).

Notas sobre la API real (verificadas con llamadas en vivo):
  - Servidor: https://www.subvenciones.gob.es/bdnstrans/api
  - Búsqueda: GET /convocatorias/busqueda?descripcion=...&pageSize=...&page=...
  - La respuesta es un objeto paginado tipo Spring: las convocatorias van en `content`.
  - Cada convocatoria de la búsqueda trae `numeroConvocatoria`, `descripcion` (el título),
    `fechaRecepcion` y los niveles de organismo `nivel1/nivel2/nivel3`. El IMPORTE no está en
    la búsqueda: vive en el detalle (`/convocatorias?numConv=...&vpd=GE` -> `presupuestoTotal`).
  - `fechaRecepcion` viene en ISO `YYYY-MM-DD` (reverificado en vivo el 2026-06-10); la API de
    búsqueda no admite filtro de fecha, así que `min_year` se aplica en cliente (`_to_hits`).
  - Respuesta en UTF-8 (se usa response.json() directamente).
  - URL pública de una convocatoria: .../bdnstrans/GE/es/convocatoria/{numeroConvocatoria}
"""

from __future__ import annotations

from typing import Any, Protocol

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import SearchHit, SearchQuery
from agente_ong.research.sources.base import Capability, SearchSource, with_retry

_API_BASE = "https://www.subvenciones.gob.es/bdnstrans/api"
_SEARCH_PATH = "/convocatorias/busqueda"
_DETAIL_PATH = "/convocatorias"  # detalle: ?numConv=...&vpd=GE
_PUBLIC_CONV_URL = "https://www.subvenciones.gob.es/bdnstrans/GE/es/convocatoria/{}"


class _HttpResponse(Protocol):
    def raise_for_status(self) -> Any: ...
    def json(self) -> Any: ...


class _HttpClient(Protocol):
    """Contrato mínimo de cliente HTTP (lo cumple httpx.Client)."""

    def get(self, url: str, **kwargs: Any) -> _HttpResponse: ...


class BdnsSource(SearchSource):
    """Búsqueda de convocatorias en la BDNS (fuente oficial de España)."""

    name = "bdns"
    is_official = True
    capabilities: frozenset[Capability] = frozenset({"search"})

    def __init__(
        self,
        config: ResearchConfig,
        client: _HttpClient | None = None,
        *,
        max_results: int = 20,
        min_year: int | None = None,
        max_detail_calls: int | None = None,
        retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self._config = config  # nota: la BDNS es pública, no usa bdns_api_key
        self._max_results = max_results
        # Año mínimo de `fechaRecepcion`; None = sin filtro. Se aplica en cliente porque la
        # API de búsqueda de la BDNS no admite filtro de fecha.
        self._min_year = min_year
        # Nº máx. de llamadas al detalle por búsqueda (R19.3); None => valor de config.
        self._max_detail_calls = (
            max_detail_calls if max_detail_calls is not None else config.bdns_max_detail_calls
        )
        self._retry_exceptions = retry_exceptions
        if client is None:
            # Import perezoso: solo se necesita httpx si no se inyecta un cliente (tests).
            import httpx

            client = httpx.Client(timeout=30, headers={"Accept": "application/json"})
        self._client = client

    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Busca convocatorias por descripción y mapea el resultado a `SearchHit`."""
        params = {
            "descripcion": query.text,
            "pageSize": self._max_results,
            "page": 0,
        }

        def call() -> Any:
            response = self._client.get(_API_BASE + _SEARCH_PATH, params=params)
            response.raise_for_status()
            return response.json()

        data = with_retry(call, exceptions=self._retry_exceptions)
        hits = self._to_hits(data)
        # R19: el min_year ya filtró en _to_hits, así que el detalle solo se pide para los
        # hits supervivientes (no se gastan llamadas en descartes — 19.2).
        self._enrich_with_detail(hits)
        return hits

    def _enrich_with_detail(self, hits: list[SearchHit]) -> None:
        """Rellena importe y plazo de los primeros N hits con su detalle (R19.1/R19.3).

        Un fallo de detalle no descarta el hit ni aborta los demás (R19.4/R19.5): el hit
        conserva sus datos de búsqueda y queda sin importe/plazo (None).
        """
        for hit in hits[: self._max_detail_calls]:
            numero = hit.url.rsplit("/", 1)[-1]
            if not numero:
                continue
            try:
                detail = self._fetch_detail(numero)
            except Exception:  # noqa: BLE001 - se aísla; nunca inventar el dato (R19.4)
                continue
            hit.amount = _format_amount(detail.get("presupuestoTotal"))
            hit.deadline = _format_deadline(detail)

    def _fetch_detail(self, numero: str) -> dict[str, Any]:
        def call() -> Any:
            response = self._client.get(
                _API_BASE + _DETAIL_PATH, params={"numConv": numero, "vpd": "GE"}
            )
            response.raise_for_status()
            return response.json()

        data = with_retry(call, exceptions=self._retry_exceptions)
        return data if isinstance(data, dict) else {}

    def _to_hits(self, data: Any) -> list[SearchHit]:
        if not isinstance(data, dict):
            return []
        hits: list[SearchHit] = []
        for item in data.get("content") or []:
            numero = item.get("numeroConvocatoria")
            if not numero:
                # Sin código de convocatoria no hay URL oficial: se descarta.
                continue
            if self._too_old(item.get("fechaRecepcion")):
                continue
            hits.append(
                SearchHit(
                    url=_PUBLIC_CONV_URL.format(numero),
                    source_name=self.name,
                    title=item.get("descripcion"),
                    snippet=self._build_snippet(item),
                    is_official=True,
                )
            )
        return hits

    def _too_old(self, fecha: Any) -> bool:
        """True si la convocatoria queda por debajo de `min_year` (formato ISO YYYY-MM-DD).

        Sin filtro configurado, o si la fecha falta o no es parseable, NO se descarta: no se
        inventa antigüedad (Requirement 10.3).
        """
        if self._min_year is None:
            return False
        try:
            year = int(str(fecha)[:4])
        except (TypeError, ValueError):
            return False
        return year < self._min_year

    @staticmethod
    def _build_snippet(item: dict[str, Any]) -> str | None:
        """Resumen breve: ruta de organismo (nivel1/2/3) y fecha de recepción."""
        levels = [item.get("nivel1"), item.get("nivel2"), item.get("nivel3")]
        organism = " / ".join(level for level in levels if level)
        fecha = item.get("fechaRecepcion")
        if organism and fecha:
            return f"{organism} (recepción: {fecha})"
        return organism or fecha or None


def _format_amount(value: Any) -> str | None:
    """Formatea `presupuestoTotal` (numérico) como '307.600 €'. None si falta o no es número."""
    if value in (None, "", 0):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # Separador de miles con punto (es-ES); sin decimales si es entero.
    entero = int(number)
    if entero == number:
        return f"{entero:,}".replace(",", ".") + " €"
    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _format_deadline(detail: dict[str, Any]) -> str | None:
    """Plazo legible desde el detalle. Prioriza la fecha de FIN (el cierre del plazo).

    Devuelve None si no hay fechas (nunca se inventa el dato, R19.4). El año del cierre
    queda en el texto para que los filtros temporales del informe lo reconozcan.
    """
    fin = detail.get("fechaFinSolicitud")
    ini = detail.get("fechaInicioSolicitud")
    abierto = detail.get("abierto")
    estado = " (abierto)" if abierto is True else " (cerrado)" if abierto is False else ""
    if fin:
        return f"hasta {fin}{estado}"
    if ini:
        return f"desde {ini}{estado}"
    return None
