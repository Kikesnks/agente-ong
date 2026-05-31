"""Registro de fuentes consultadas (`SourceLedger`), persistente entre investigaciones.

El ledger cumple un doble papel:

  1. **No repetir** dentro de la investigación en curso: lleva una *vista en memoria* de las
     URLs/consultas ya tocadas (`mark_queried` / `seen`), evitando reprocesarlas y los
     ciclos al seguir enlaces (Requirements 5.1, 5.2, 6.2).

  2. **Acumular conocimiento** entre investigaciones: cada fuente se persiste vía
     `ResearchStore` con su resumen (`content_summary`) y fecha (`captured_at`); en
     investigaciones futuras, `find_by_topic` recupera esas entradas como PISTAS
     (Requirement 5.3).

Distinción importante: `seen()` consulta solo la vista en memoria (lo tocado en ESTA
investigación). Las entradas previas del store son pistas reutilizables, no algo a omitir:
un dato crítico ya conocido puede revisitarse para revalidarlo (ver política de revalidación
del diseño). Por eso `find_by_topic` no marca nada como visto.

Las claves se canonicalizan: las URLs con `normalize_url` (deduplicación de equivalentes) y
las consultas con un hash estable de su texto.
"""

from __future__ import annotations

import hashlib

from agente_ong.research.models import LedgerEntry, LedgerKind, LedgerOutcome, SourceRef
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.urlnorm import normalize_url


def _canonical_key(raw: str, kind: LedgerKind) -> str:
    """Clave canónica de una entrada: URL normalizada o hash del texto de la consulta."""
    if kind == "url":
        return normalize_url(raw)
    text = (raw or "").strip().lower()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"query:{digest}"


class SourceLedger:
    """Registro de fuentes consultadas con vista en memoria + persistencia por puerto."""

    def __init__(self, store: ResearchStore) -> None:
        self._store = store
        # Vista en memoria de la investigación en curso, indexada por clave canónica.
        self._view: dict[str, LedgerEntry] = {}

    # --- No repetir (vista en memoria de la investigación en curso) ---

    def mark_queried(self, key: str, kind: LedgerKind = "url") -> str:
        """Marca una URL/consulta como tocada en esta investigación. Devuelve su clave canónica.

        Si aún no existía, crea una entrada mínima en estado `pending` (se completará luego
        con `record`).
        """
        ckey = _canonical_key(key, kind)
        if ckey not in self._view:
            self._view[ckey] = LedgerEntry(key=ckey, kind=kind, outcome="pending")
        return ckey

    def seen(self, key: str, kind: LedgerKind = "url") -> bool:
        """True si la URL/consulta ya fue tocada en ESTA investigación (vista en memoria)."""
        return _canonical_key(key, kind) in self._view

    # --- Registrar resultado (con resumen y procedencia) ---

    def record(
        self,
        key: str,
        *,
        kind: LedgerKind,
        outcome: LedgerOutcome,
        content_summary: str = "",
        topics: list[str] | None = None,
        source_ref: SourceRef | None = None,
    ) -> LedgerEntry:
        """Guarda/actualiza la entrada de una fuente con su resultado, resumen y temáticas.

        `captured_at` se fija al momento del registro (default del modelo). La entrada queda
        en la vista en memoria; se persiste con `flush()`.
        """
        ckey = _canonical_key(key, kind)
        entry = LedgerEntry(
            key=ckey,
            kind=kind,
            outcome=outcome,
            content_summary=content_summary,
            topics=list(topics or []),
            source_ref=source_ref,
        )
        self._view[ckey] = entry
        return entry

    # --- Recall de pistas previas (persistente) ---

    def find_by_topic(self, terms: list[str]) -> list[LedgerEntry]:
        """Devuelve pistas relevantes por temática: entradas previas del store más las de la
        investigación en curso que casen. La vista en memoria tiene prioridad (más fresca).

        No marca nada como visto: las pistas pueden revisitarse para revalidación.
        """
        results: dict[str, LedgerEntry] = {}
        for entry in self._store.find_ledger_by_topic(terms):
            results[entry.key] = entry
        wanted = {t.lower() for t in terms if t}
        if wanted:
            for entry in self._view.values():
                if wanted & {topic.lower() for topic in entry.topics}:
                    results[entry.key] = entry
        return list(results.values())

    # --- Volcado / inspección ---

    def entries(self) -> list[LedgerEntry]:
        """Todas las entradas de la investigación en curso (vista en memoria)."""
        return list(self._view.values())

    def flush(self) -> None:
        """Persiste todas las entradas de la vista en memoria a través del `ResearchStore`."""
        for entry in self._view.values():
            self._store.save_ledger_entry(entry)
