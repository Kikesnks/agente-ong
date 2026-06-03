"""Orquestación del agente investigador (grafo LangGraph).

`ResearchGraph` sostiene los colaboradores de la investigación (fuentes, ledger, política de
verificación, limitador de profundidad y collector de entrenamiento) y define los nodos del
grafo como métodos. El flujo objetivo es:

    plan -> recall_ledger -> search -> read_deep -> verify -> (loop | ask_user | compile_report)

Esta entrega cubre el estado compartido (`ResearchState`) y los dos primeros nodos:
  - `plan`: deriva las consultas de búsqueda a partir de la petición e inicializa contadores.
  - `recall_ledger`: recupera pistas de investigaciones previas por temática (Requirement 5.3)
    para priorizar y evitar reprocesar (Requirement 6.2); las deja en `reused_from_ledger`.

Los nodos search/read_deep/verify/ask_user/compile_report y el cableado del `StateGraph` se
añaden en las tareas 26-27.
"""

from __future__ import annotations

from typing import TypedDict

from agente_ong.research.collector import TrainingCollector
from agente_ong.research.config import ResearchConfig
from agente_ong.research.depth import DepthLimiter
from agente_ong.research.ledger import SourceLedger
from agente_ong.research.models import (
    FailedSource,
    FetchedDocument,
    GrantOpportunity,
    LedgerEntry,
    ResearchRequest,
    SearchHit,
    SearchQuery,
    StoredResource,
    Unresolved,
)
from agente_ong.research.sources.base import SearchSource
from agente_ong.research.verification import VerificationPolicy


class ResearchState(TypedDict, total=False):
    """Estado compartido que fluye por los nodos del grafo de investigación."""

    request: ResearchRequest
    queries: list[SearchQuery]
    reused_from_ledger: list[LedgerEntry]
    hits: list[SearchHit]
    documents: list[FetchedDocument]
    opportunities: list[GrantOpportunity]
    resources: list[StoredResource]
    unresolved: list[Unresolved]
    failed_sources: list[FailedSource]
    # Contadores para el control de profundidad/coste (DepthLimiter).
    depth: int
    pages_fetched: int
    queries_made: int


class ResearchGraph:
    """Define los nodos del grafo de investigación sobre un conjunto de colaboradores."""

    def __init__(
        self,
        sources: list[SearchSource],
        ledger: SourceLedger,
        policy: VerificationPolicy,
        limiter: DepthLimiter,
        collector: TrainingCollector | None = None,
        config: ResearchConfig | None = None,
    ) -> None:
        self._sources = list(sources)
        self._ledger = ledger
        self._policy = policy
        self._limiter = limiter
        self._collector = collector
        self._config = config or ResearchConfig()

    # --- Nodo: plan ---

    def plan(self, state: ResearchState) -> dict:
        """Deriva las consultas de búsqueda e inicializa los contadores de la investigación."""
        request = state["request"]
        return {
            "queries": self._derive_queries(request),
            "depth": 0,
            "pages_fetched": 0,
            "queries_made": 0,
        }

    @staticmethod
    def _derive_queries(request: ResearchRequest) -> list[SearchQuery]:
        """Genera consultas a partir de los términos: una combinada y, si hay varios, cada una.

        Deduplica de forma insensible a mayúsculas para no lanzar la misma consulta dos veces.
        """
        terms = [t.strip() for t in request.query_terms if t and t.strip()]
        queries: list[SearchQuery] = []
        seen: set[str] = set()

        def add(text: str) -> None:
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                queries.append(SearchQuery(text=text))

        if terms:
            add(" ".join(terms))  # consulta combinada (la más específica)
            if len(terms) > 1:
                for term in terms:
                    add(term)  # consultas individuales para ampliar cobertura
        return queries

    # --- Nodo: recall_ledger ---

    def recall_ledger(self, state: ResearchState) -> dict:
        """Recupera pistas de investigaciones previas por temática (no las marca como vistas)."""
        request = state["request"]
        hints = self._ledger.find_by_topic(request.query_terms)
        return {"reused_from_ledger": hints}
