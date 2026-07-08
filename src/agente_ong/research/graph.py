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

from langgraph.graph import END, START, StateGraph

from agente_ong.research.collector import TrainingCollector
from agente_ong.research.config import ResearchConfig
from agente_ong.research.depth import DepthLimiter
from agente_ong.research.ledger import SourceLedger
from agente_ong.research.models import (
    Claim,
    FailedSource,
    FetchedDocument,
    GrantOpportunity,
    LedgerEntry,
    ResearchReport,
    ResearchRequest,
    SearchHit,
    SearchQuery,
    SourceRef,
    StoredResource,
    Unresolved,
    VerificationStatus,
)
from agente_ong.research.ods_catalogo import OdsEntry
from agente_ong.research.sources.base import SearchSource
from agente_ong.research.textclean import clean_text, snippet
from agente_ong.research.triage import best_result_type, classify_hit
from agente_ong.research.urlnorm import normalize_url
from agente_ong.research.verification import VerificationPolicy, dedupe_refs

# Longitud máxima del resumen que se guarda en el ledger por cada documento leído.
_SUMMARY_MAX_CHARS = 280

# --- ODS elegidos por el usuario (R25) ---
_ODS_BASE_TERM = "convocatoria"  # término base de R16 que ancla cada query ODS


class ResearchState(TypedDict, total=False):
    """Estado compartido que fluye por los nodos del grafo de investigación."""

    request: ResearchRequest
    # ODS elegidos por el usuario desde la UI (R25). None/ausente hasta que exista T26.
    selected_ods: list[OdsEntry]
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
    # Informe final compilado (compile_report).
    report: ResearchReport


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
        selected_ods = state.get("selected_ods")
        return {
            "queries": self._derive_queries(request, selected_ods),
            "depth": 0,
            "pages_fetched": 0,
            "queries_made": 0,
        }

    @staticmethod
    def _derive_queries(
        request: ResearchRequest, selected_ods: list[OdsEntry] | None = None
    ) -> list[SearchQuery]:
        """Genera consultas a partir de los términos y de los ODS elegidos por el usuario.

        Deduplica de forma insensible a mayúsculas para no lanzar la misma consulta dos veces.

        R25: cada ODS elegido por el usuario genera una query ODS (N elegidos → N queries).
        Decisión B1 (R25.3): si `selected_ods` es `None` o vacío, se lanza `ValueError`
        explícito; no hay fallback silencioso al vocabulario fijo de R24.
        """
        if not selected_ods:
            raise ValueError(
                "No se pueden derivar las queries: selected_ods está vacío o es None "
                "(decisión B1, R25.3 — sin fallback al vocabulario fijo de R24)"
            )

        terms = [t.strip() for t in request.query_terms if t and t.strip()]
        queries: list[SearchQuery] = []
        seen: set[str] = set()

        def add(text: str) -> None:
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                # Propaga el contexto de búsqueda a cada query (lo aprovecha Tavily).
                queries.append(SearchQuery(text=text, search_context=request.search_context))

        if terms:
            add(" ".join(terms))  # consulta combinada (la más específica)
            if len(terms) > 1:
                for term in terms:
                    if len(term.split()) > 1:
                        add(term)  # consultas individuales solo si el término es multi-palabra
                    # los términos de una sola palabra ya van en la consulta combinada

        # R25: una query por cada ODS elegido por el usuario (N elegidos → N queries).
        for entry in selected_ods:
            add(f"{_ODS_BASE_TERM} ODS {entry['numero']} {entry['nombre']}")

        return queries

    # --- Nodo: recall_ledger ---

    def recall_ledger(self, state: ResearchState) -> dict:
        """Recupera pistas de investigaciones previas por temática (no las marca como vistas)."""
        request = state["request"]
        hints = self._ledger.find_by_topic(request.query_terms)
        return {"reused_from_ledger": hints}

    # --- Nodo: search ---

    def search(self, state: ResearchState) -> dict:
        """Lanza las consultas contra las fuentes de búsqueda y agrega los resultados.

        Registra cada consulta en el ledger para no repetirla; el fallo de una fuente se
        anota en `failed_sources` sin abortar el resto (NFR Reliability).
        """
        queries = state.get("queries", [])
        hits = list(state.get("hits", []))
        failed = list(state.get("failed_sources", []))
        queries_made = state.get("queries_made", 0)
        pages = state.get("pages_fetched", 0)
        depth = state.get("depth", 0)

        search_sources = self._active_sources(state["request"], "search")

        for query in queries:
            if self._ledger.seen(query.text, kind="query"):
                continue
            if not self._limiter.can_expand(depth, pages, queries_made):
                break  # se alcanzó el tope de consultas/coste (Requirement 6.3)
            self._ledger.mark_queried(query.text, kind="query")
            queries_made += 1
            for source in search_sources:
                try:
                    results = source.search(query)
                except Exception as exc:  # noqa: BLE001 - se reporta, no se aborta
                    failed.append(FailedSource(source_name=source.name, error=str(exc)))
                    continue
                # R20/23.3: se pre-clasifica cada hit aquí para que `read_deep` (que se
                # ejecuta antes de `verify`) ya pueda usar `hit.result_type` en su gating.
                for hit in results:
                    hit.result_type = classify_hit(hit)
                hits.extend(results)

        # No se deduplican los hits aquí a propósito: `verify` los agrupa por URL para la
        # verificación cruzada (dos fuentes con la misma URL => VERIFIED). La deduplicación
        # de lecturas la garantiza el ledger en `read_deep`.
        return {
            "hits": hits,
            "failed_sources": failed,
            "queries_made": queries_made,
        }

    # --- Nodo: read_deep ---

    def read_deep(self, state: ResearchState) -> dict:
        """Profundiza leyendo las URLs de los hits y siguiendo sus enlaces relevantes.

        Recorrido en anchura limitado por `DepthLimiter` (profundidad/páginas), por
        `reader_max_pages` (R23.4, gana el menor frente a `max_pages`) y por el ledger (no
        re-visita URLs ya vistas, evitando ciclos; Requirements 6.1, 6.2).

        R23.3: en modo "calls" la frontera solo se siembra con las `direct_urls` del
        usuario (siempre) y los hits `result_type == "convocatoria_probable"`; los
        enlaces salientes heredan la elegibilidad de su página origen (ya elegible al
        estar en la frontera). En modo "training" el gating no aplica (R20 reserva
        "documento_informativo"/"desconocido" para material que SÍ es relevante como
        ejemplo de entrenamiento): todos los hits siembran la frontera, como antes de R23.
        """
        documents = list(state.get("documents", []))
        failed = list(state.get("failed_sources", []))
        pages = state.get("pages_fetched", 0)
        queries_made = state.get("queries_made", 0)
        depth_reached = state.get("depth", 0)
        topics = state["request"].query_terms

        fetch_sources = self._active_sources(state["request"], "fetch")
        if not fetch_sources:
            return {"documents": documents}
        primary, *fallbacks = fetch_sources
        firecrawl_calls_left = self._config.firecrawl_max_calls
        # R23.4: reader_max_pages coexiste con max_pages; gana el menor.
        max_pages = min(self._limiter.max_pages, self._config.reader_max_pages)

        # Frontera (url, profundidad). Las URLs directas del usuario y los hits elegibles
        # están en el nivel 1; las directas van primero para que se lean aunque se agote el
        # presupuesto de páginas (Requirement 9.1/9.4). El ledger evita la doble lectura si
        # una URL directa coincide con un hit.
        frontier: list[tuple[str, int]] = [
            (url, 1) for url in state["request"].direct_urls
        ]
        calls_mode = state["request"].mode == "calls"
        frontier.extend(
            (hit.url, 1)
            for hit in state.get("hits", [])
            if not calls_mode or hit.result_type == "convocatoria_probable"
        )

        while frontier:
            url, level = frontier.pop(0)
            if self._ledger.seen(url, kind="url"):
                continue
            # ¿Podemos descender un nivel más y leer otra página?
            if not self._limiter.can_expand(level - 1, pages, queries_made) or pages >= max_pages:
                break

            self._ledger.mark_queried(url, kind="url")
            doc, fetcher, firecrawl_calls_left = self._fetch_with_fallback(
                url, primary, fallbacks, firecrawl_calls_left, failed
            )
            if doc is None:
                self._ledger.record(url, kind="url", outcome="error")
                continue

            documents.append(doc)
            pages += 1
            depth_reached = max(depth_reached, level)
            self._ledger.record(
                url,
                kind="url",
                outcome="useful",
                content_summary=_summarize(doc),
                topics=topics,
                source_ref=SourceRef(
                    url=doc.url, source_name=fetcher.name, is_official=fetcher.is_official
                ),
            )

            # Encolar enlaces salientes al siguiente nivel solo si aún cabe profundizar.
            if level < self._limiter.max_depth:
                for link in doc.outbound_links:
                    if not self._ledger.seen(link, kind="url"):
                        frontier.append((link, level + 1))

        return {
            "documents": documents,
            "failed_sources": failed,
            "pages_fetched": pages,
            "depth": depth_reached,
        }

    @staticmethod
    def _fetch_with_fallback(
        url: str,
        primary: SearchSource,
        fallbacks: list[SearchSource],
        firecrawl_calls_left: int,
        failed: list[FailedSource],
    ) -> tuple[FetchedDocument | None, SearchSource | None, int]:
        """Lee `url` con `primary`; si falla, recurre a `fallbacks` mientras quede cupo.

        R23.2: el primario es el lector propio (sin coste); el fallback (Firecrawl) se
        invoca como máximo `firecrawl_calls_left` veces. R23.5: un fallo no descarta la
        URL — devuelve `(None, None, cupo)` y el llamador lo registra como error sin
        abortar el resto.
        """
        try:
            return primary.fetch(url), primary, firecrawl_calls_left
        except Exception as exc:  # noqa: BLE001 - se reporta, no se aborta
            failed.append(FailedSource(source_name=primary.name, error=str(exc)))

        for fallback in fallbacks:
            if firecrawl_calls_left <= 0:
                break
            firecrawl_calls_left -= 1
            try:
                return fallback.fetch(url), fallback, firecrawl_calls_left
            except Exception as exc:  # noqa: BLE001 - se reporta, no se aborta
                failed.append(FailedSource(source_name=fallback.name, error=str(exc)))

        return None, None, firecrawl_calls_left

    # --- Helpers ---

    def _active_sources(self, request: ResearchRequest, capability: str) -> list[SearchSource]:
        """Fuentes con la capacidad dada, restringidas por modo y por `enabled_sources`.

        Una fuente cuyo `excluded_modes` incluye el modo de la investigación no se consulta
        (R15: TED fuera de subvenciones). `enabled_sources is None` => todas las fuentes
        restantes (comportamiento previo a la UI, Requirement 9.2/9.3). Las fuentes con
        `user_selectable=False` (R23: Firecrawl, fallback de configuración) nunca se
        excluyen por `enabled_sources` — el usuario no las elige.
        """
        sources = [
            s
            for s in self._sources
            if s.supports(capability) and request.mode not in s.excluded_modes
        ]
        if request.enabled_sources is None:
            return sources
        return [
            s
            for s in sources
            if s.name in request.enabled_sources or not s.user_selectable
        ]

    # --- Nodo: verify ---

    def verify(self, state: ResearchState) -> dict:
        """Procesa los resultados: construye y verifica convocatorias, o captura entrenamiento.

        En modo 'calls' agrupa los hits en `GrantOpportunity` y clasifica cada dato con
        `VerificationPolicy`, revalidando los críticos con valor (Requirements 4.1, 4.3). En
        modo 'training' pasa los documentos por el `TrainingCollector`.
        """
        request = state["request"]
        if request.mode == "training":
            resources = list(state.get("resources", []))
            if self._collector is not None:
                for doc in state.get("documents", []):
                    resources.append(self._collector.collect(doc, tags=request.query_terms))
            return {"resources": resources}

        opportunities = self._build_opportunities(state.get("hits", []))
        for opp in opportunities:
            for claim in (opp.amount, opp.deadline):
                if claim.value is not None:
                    self._policy.needs_revalidation(claim, intent=request.intent)
        return {"opportunities": opportunities}

    def _build_opportunities(self, hits: list[SearchHit]) -> list[GrantOpportunity]:
        """Agrupa hits por URL (misma convocatoria) y construye `GrantOpportunity` verificadas.

        Las fuentes que coinciden en una misma URL son el respaldo cruzado de esa convocatoria:
        dos fuentes -> VERIFIED; una oficial -> OFFICIAL_UNCROSSED; una no oficial ->
        UNCROSSED_UNVERIFIED. El importe y el plazo no vienen en la búsqueda (NOT_FOUND): se
        marcan como críticos para que `ask_user` los recoja.
        """
        groups: dict[str, list[SearchHit]] = {}
        for hit in hits:
            groups.setdefault(normalize_url(hit.url), []).append(hit)

        opportunities: list[GrantOpportunity] = []
        for url_key, group in groups.items():
            refs = [
                SourceRef(url=h.url, source_name=h.source_name, is_official=h.is_official)
                for h in group
            ]
            title_val = next((h.title for h in group if h.title), None)
            # R18: el snippet del organismo se limpia de plantilla web y se acota (hoy podía
            # llegar con páginas enteras de menús/cookies).
            organism_raw = next((h.snippet for h in group if h.snippet), None)
            organism_val = (
                snippet(clean_text(organism_raw), self._config.organism_max_chars) or None
                if organism_raw
                else None
            )
            url_val = group[0].url

            # R19: importe y plazo pueden venir del detalle de la fuente (hoy BDNS). El
            # claim se respalda con las refs de los hits que aportaron el dato → pasa de
            # NOT_FOUND a OFFICIAL_UNCROSSED, trazable. Sin dato => None => NOT_FOUND.
            amount_val, amount_refs = self._first_with(group, "amount")
            deadline_val, deadline_refs = self._first_with(group, "deadline")

            title = self._classified(Claim(field="titulo", value=title_val), refs)
            url_claim = self._classified(Claim(field="url", value=url_val), refs)
            organism = self._classified(Claim(field="organismo", value=organism_val), refs)
            amount = self._classified(
                Claim(field="importe", value=amount_val, is_critical=True), amount_refs
            )
            deadline = self._classified(
                Claim(field="plazo", value=deadline_val, is_critical=True), deadline_refs
            )
            scope = self._classified(Claim(field="ambito"), [])

            # R20: pre-clasificación heurística — el mejor tipo de los hits del grupo.
            result_type = best_result_type([classify_hit(h) for h in group])

            opportunities.append(
                GrantOpportunity(
                    title=title,
                    organism=organism,
                    amount=amount,
                    deadline=deadline,
                    scope=scope,
                    url=url_claim,
                    overall_status=title.status,
                    result_type=result_type,
                )
            )
        return opportunities

    @staticmethod
    def _first_with(group: list[SearchHit], attr: str) -> tuple[str | None, list[SourceRef]]:
        """Primer valor no vacío de `attr` (amount/deadline) en el grupo y su procedencia.

        Devuelve `(valor, [SourceRef])`; si ningún hit lo aporta, `(None, [])` -> el claim
        quedará NOT_FOUND (R19.4, nunca inventar).
        """
        for hit in group:
            value = getattr(hit, attr, None)
            if value:
                ref = SourceRef(
                    url=hit.url, source_name=hit.source_name, is_official=hit.is_official
                )
                return value, [ref]
        return None, []

    def _classified(self, claim: Claim, refs: list[SourceRef]) -> Claim:
        """Asigna a `claim` sus fuentes de respaldo (sin URLs repetidas, R14.3) y su estado."""
        claim.sources = dedupe_refs(refs)
        claim.status = self._policy.classify(claim, claim.sources)
        return claim

    # --- Nodo: ask_user ---

    def ask_user(self, state: ResearchState) -> dict:
        """Declara explícitamente lo que falta y qué ayuda se necesita (Requirement 3.1)."""
        request = state["request"]
        unresolved = list(state.get("unresolved", []))

        if request.mode == "training":
            if not state.get("resources"):
                unresolved.append(
                    Unresolved(
                        topic="entrenamiento",
                        reason="No se capturaron proyectos de ejemplo para los términos dados.",
                        help_needed="Aporta URLs de proyectos aprobados o material de referencia.",
                    )
                )
            return {"unresolved": unresolved}

        opportunities = state.get("opportunities", [])
        if not opportunities:
            unresolved.append(
                Unresolved(
                    topic="convocatorias",
                    reason="No se encontraron convocatorias para los términos dados.",
                    help_needed=(
                        "Aporta palabras clave más específicas, un ámbito (país/UE) o la "
                        "URL/portal de la convocatoria."
                    ),
                )
            )
            return {"unresolved": unresolved}

        # Datos críticos no hallados en la búsqueda (importe/plazo viven en el detalle).
        missing_amount = sum(
            1 for o in opportunities if o.amount.status == VerificationStatus.NOT_FOUND
        )
        if missing_amount:
            unresolved.append(
                Unresolved(
                    topic="importe",
                    reason=f"{missing_amount} convocatoria(s) sin importe confirmado en la búsqueda.",
                    help_needed="El importe suele estar en el detalle; confirma si procede consultarlo.",
                )
            )
        missing_deadline = sum(
            1 for o in opportunities if o.deadline.status == VerificationStatus.NOT_FOUND
        )
        if missing_deadline:
            unresolved.append(
                Unresolved(
                    topic="plazo",
                    reason=f"{missing_deadline} convocatoria(s) sin plazo confirmado en la búsqueda.",
                    help_needed="El plazo suele estar en el detalle; confirma si procede consultarlo.",
                )
            )
        return {"unresolved": unresolved}

    # --- Nodo: compile_report ---

    def compile_report(self, state: ResearchState) -> dict:
        """Arma el `ResearchReport` final y persiste el ledger (`flush`)."""
        request = state["request"]
        report = ResearchReport(
            mode=request.mode,
            opportunities=list(state.get("opportunities", [])),
            resources=list(state.get("resources", [])),
            ledger=self._ledger.entries(),
            reused_from_ledger=list(state.get("reused_from_ledger", [])),
            unresolved=list(state.get("unresolved", [])),
            failed_sources=list(state.get("failed_sources", [])),
        )
        self._ledger.flush()
        return {"report": report}

    # --- Enrutado (condición continue?) y construcción del grafo ---

    @staticmethod
    def _route_after_verify(state: ResearchState) -> str:
        """Decide tras verify: pedir ayuda al usuario si hay lagunas, o compilar el informe."""
        request = state["request"]
        if request.mode == "training":
            has_gaps = not state.get("resources")
        else:
            opportunities = state.get("opportunities", [])
            has_gaps = (not opportunities) or any(
                o.amount.status == VerificationStatus.NOT_FOUND
                or o.deadline.status == VerificationStatus.NOT_FOUND
                for o in opportunities
            )
        return "ask_user" if has_gaps else "compile_report"

    def build(self):
        """Construye y compila el grafo LangGraph de la investigación.

        Nota de diseño: el `continue?` del diseño se materializa como el enrutado
        verify -> {ask_user | compile_report}. No se cablea un bucle de vuelta a `search`
        porque `plan` ya genera todas las consultas y `read_deep` recorre los enlaces hasta
        `max_depth` en una pasada; un bucle ingenuo no produciría trabajo nuevo (consultas ya
        vistas, sin hits nuevos) y podría no terminar mientras quedara presupuesto. Avanzar
        garantiza la terminación; el `DepthLimiter` y el ledger acotan el trabajo.
        """
        builder = StateGraph(ResearchState)
        builder.add_node("plan", self.plan)
        builder.add_node("recall_ledger", self.recall_ledger)
        builder.add_node("search", self.search)
        builder.add_node("read_deep", self.read_deep)
        builder.add_node("verify", self.verify)
        builder.add_node("ask_user", self.ask_user)
        builder.add_node("compile_report", self.compile_report)

        builder.add_edge(START, "plan")
        builder.add_edge("plan", "recall_ledger")
        builder.add_edge("recall_ledger", "search")
        builder.add_edge("search", "read_deep")
        builder.add_edge("read_deep", "verify")
        builder.add_conditional_edges(
            "verify",
            self._route_after_verify,
            {"ask_user": "ask_user", "compile_report": "compile_report"},
        )
        builder.add_edge("ask_user", "compile_report")
        builder.add_edge("compile_report", END)
        return builder.compile()


def _summarize(doc: FetchedDocument) -> str:
    """Resumen breve del contenido de un documento para guardar como pista en el ledger.

    R18: limpia los elementos de plantilla web antes de truncar, para que la pista del
    ledger no arrastre menús/cookies.
    """
    return snippet(clean_text(doc.content_text), _SUMMARY_MAX_CHARS)
