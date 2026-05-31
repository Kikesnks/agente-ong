"""Puerto de persistencia del agente investigador.

`ResearchStore` es la interfaz (puerto, patrón Ports & Adapters) que abstrae *dónde* se
persisten el registro de fuentes (`SourceLedger`) y el índice de recursos capturados. El
núcleo del módulo depende solo de esta interfaz, nunca de ENGRAM ni de ninguna tecnología
concreta — eso es lo que mantiene el investigador portable (ver Requirement 7).

Adaptadores previstos:
  - `InMemoryStore`  : por defecto, portátil; recall solo dentro del proceso (tarea 9).
  - `EngramStore`    : persiste en ENGRAM, habilitando recall entre sesiones (tarea 30).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agente_ong.research.models import LedgerEntry, StoredResource


class ResearchStore(ABC):
    """Contrato de persistencia para el ledger y el índice de capturas.

    Una implementación debe persistir las entradas de ledger de forma que puedan recuperarse
    por clave (`get_ledger_entry`) y por temática (`find_ledger_by_topic`), y debe llevar un
    índice de recursos capturados consultable por URL (`has_url`) para evitar re-descargas.
    """

    # --- Ledger de fuentes consultadas ---

    @abstractmethod
    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        """Guarda o actualiza una entrada del ledger (clave = `entry.key`)."""
        raise NotImplementedError

    @abstractmethod
    def get_ledger_entry(self, key: str) -> LedgerEntry | None:
        """Devuelve la entrada de ledger con esa clave, o None si no existe."""
        raise NotImplementedError

    @abstractmethod
    def find_ledger_by_topic(self, terms: list[str]) -> list[LedgerEntry]:
        """Recall por temática: entradas cuyo `topics` casa con alguno de `terms`.

        Sirve para reutilizar como PISTAS las fuentes ya conocidas en investigaciones
        previas (nunca como dato definitivo).
        """
        raise NotImplementedError

    # --- Índice de recursos de entrenamiento capturados ---

    @abstractmethod
    def has_url(self, url: str) -> bool:
        """True si esa URL ya fue capturada (para no descargarla de nuevo)."""
        raise NotImplementedError

    @abstractmethod
    def add_resource(self, resource: StoredResource) -> None:
        """Registra un recurso capturado en el índice."""
        raise NotImplementedError

    @abstractmethod
    def list_resources(self) -> list[StoredResource]:
        """Devuelve todos los recursos capturados registrados."""
        raise NotImplementedError
