"""Interfaz de fuentes de búsqueda/lectura (`SearchSource`) y utilidades comunes.

`SearchSource` es la abstracción (patrón Strategy) que desacopla al agente de los proveedores
concretos (Tavily, Firecrawl, BDNS, TED): el grafo trabaja contra esta interfaz y nunca
contra una API concreta, lo que permite añadir o sustituir fuentes sin tocar la lógica
(Requirement 7.3).

No todas las fuentes ofrecen las mismas capacidades: unas solo buscan (`search`), otras solo
leen en profundidad (`fetch`). Cada fuente declara sus `capabilities`; `supports()` permite
consultarlas, y llamar a una capacidad no soportada lanza `NotImplementedError`.

`with_retry` es el helper reutilizable de reintentos con backoff exponencial para absorber
fallos transitorios de red/rate-limit sin abortar la investigación (NFR Reliability).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Literal, TypeVar

from agente_ong.research.models import FetchedDocument, ResearchMode, SearchHit, SearchQuery

Capability = Literal["search", "fetch"]

T = TypeVar("T")


def with_retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Ejecuta `func` reintentando ante `exceptions` con backoff exponencial.

    Espera base_delay * 2**i entre intentos. Si se agotan los intentos, re-lanza la última
    excepción. `sleep` es inyectable para poder testear sin esperas reales; si es None se usa
    `time.sleep` (resuelto en tiempo de llamada, lo que permite neutralizarlo con monkeypatch).
    """
    do_sleep = sleep if sleep is not None else time.sleep
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return func()
        except exceptions as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
            do_sleep(base_delay * (2**attempt))
    # Inalcanzable, pero satisface a los analizadores de tipos.
    assert last_exc is not None
    raise last_exc


class SearchSource(ABC):
    """Fuente intercambiable de búsqueda y/o lectura profunda."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador corto de la fuente (p.ej. 'tavily', 'bdns')."""

    @property
    @abstractmethod
    def is_official(self) -> bool:
        """True si es una fuente oficial (BDNS, TED, boletines): fiable sin cruzar."""

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[Capability]:
        """Capacidades que ofrece la fuente: {'search'}, {'fetch'} o ambas."""

    # Modos de investigación en los que la fuente NO debe consultarse (R15 de
    # investigador-v2). Default vacío = disponible en todos los modos (retrocompatible).
    # P.ej. TED publica contratación pública, no subvenciones: se excluye de "calls".
    excluded_modes: frozenset[ResearchMode] = frozenset()

    # False si la fuente no es una opción activable por el usuario (R23 de
    # investigador-v2): `_active_sources` no la excluye aunque falte de
    # `request.enabled_sources` (p.ej. Firecrawl, fallback de configuración invisible en
    # la UI). Default True = comportamiento previo (retrocompatible).
    user_selectable: bool = True

    def supports(self, capability: Capability) -> bool:
        """True si la fuente ofrece la capacidad indicada."""
        return capability in self.capabilities

    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Busca y devuelve resultados. Las fuentes que buscan deben sobrescribirlo."""
        raise NotImplementedError(f"La fuente '{self.name}' no soporta 'search'")

    def fetch(self, url: str) -> FetchedDocument:
        """Lee una URL en profundidad. Las fuentes que leen deben sobrescribirlo."""
        raise NotImplementedError(f"La fuente '{self.name}' no soporta 'fetch'")
