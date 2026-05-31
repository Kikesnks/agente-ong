"""Adaptador de persistencia en memoria.

`InMemoryStore` implementa `ResearchStore` con estructuras en memoria. Es el adaptador por
defecto y portátil del módulo: no requiere ENGRAM ni ninguna infraestructura externa, por lo
que sirve para uso standalone y para tests. El recall solo persiste mientras vive el proceso.
"""

from __future__ import annotations

from agente_ong.research.models import LedgerEntry, StoredResource
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.urlnorm import normalize_url


class InMemoryStore(ResearchStore):
    """Implementación en memoria del puerto `ResearchStore`."""

    def __init__(self) -> None:
        # Ledger indexado por clave (dict conserva el orden de inserción).
        self._ledger: dict[str, LedgerEntry] = {}
        # Recursos capturados, en orden, y conjunto de URLs normalizadas para has_url O(1).
        self._resources: list[StoredResource] = []
        self._resource_urls: set[str] = set()

    # --- Ledger ---

    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        # Upsert por clave: una clave repetida actualiza la entrada existente.
        self._ledger[entry.key] = entry

    def get_ledger_entry(self, key: str) -> LedgerEntry | None:
        return self._ledger.get(key)

    def find_ledger_by_topic(self, terms: list[str]) -> list[LedgerEntry]:
        # Recall por temática: una entrada casa si alguno de sus `topics` coincide con alguno
        # de los términos buscados (comparación insensible a mayúsculas). Sin términos => [].
        wanted = {t.lower() for t in terms if t}
        if not wanted:
            return []
        return [
            entry
            for entry in self._ledger.values()
            if wanted & {topic.lower() for topic in entry.topics}
        ]

    # --- Índice de recursos capturados ---

    def has_url(self, url: str) -> bool:
        return normalize_url(url) in self._resource_urls

    def add_resource(self, resource: StoredResource) -> None:
        self._resources.append(resource)
        self._resource_urls.add(normalize_url(resource.source_url))

    def list_resources(self) -> list[StoredResource]:
        # Copia para que el llamador no mute el estado interno.
        return list(self._resources)
