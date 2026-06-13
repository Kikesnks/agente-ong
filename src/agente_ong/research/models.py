"""Modelos de dominio del agente investigador.

Define los tipos que viajan por el grafo de investigación: procedencia (`SourceRef`),
búsqueda y lectura (`SearchQuery`, `SearchHit`, `FetchedDocument`), datos verificables
(`Claim`, `GrantOpportunity`), registro persistente (`LedgerEntry`), captura de
entrenamiento (`StoredResource`) y los contenedores de entrada/salida (`ResearchRequest`,
`ResearchReport`).

Todo dato factual es trazable a su fuente (ver requisitos de veracidad de la spec) y el
estado de verificación se expresa con `VerificationStatus` más el flag ortogonal `stale`
(caducidad).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal

# --- Alias de tipos cerrados (Literals) ---
ResearchMode = Literal["calls", "training"]
Intent = Literal["explore", "use_in_proposal"]
LedgerKind = Literal["query", "url"]
LedgerOutcome = Literal["useful", "empty", "error", "pending"]
CaptureMode = Literal["download", "text_copy"]


def _utcnow() -> datetime:
    """Marca temporal actual con zona UTC (para captured_at / retrieved_at)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tarea 3 — Enums y modelos base (procedencia, búsqueda y lectura)
# ---------------------------------------------------------------------------


class VerificationStatus(Enum):
    """Estado de verificación de un dato factual.

    La caducidad NO es un estado: se expresa con el flag `stale` del `Claim`, ortogonal a
    este enum.
    """

    VERIFIED = "verified"  # corroborado por >=2 fuentes
    OFFICIAL_UNCROSSED = "official_uncrossed"  # 1 fuente oficial (aceptable, no cruzada)
    UNCROSSED_UNVERIFIED = "uncrossed_unverified"  # 1 fuente no oficial (preocupante)
    CONFLICTING = "conflicting"  # fuentes contradictorias
    NOT_FOUND = "not_found"  # sin fuentes


@dataclass
class SourceRef:
    """Referencia trazable a una fuente concreta de un dato."""

    url: str
    source_name: str  # tavily | firecrawl | bdns | ted | ...
    is_official: bool
    retrieved_at: datetime = field(default_factory=_utcnow)


@dataclass
class SearchQuery:
    """Consulta de búsqueda a lanzar contra una o varias fuentes."""

    text: str
    source_hint: str | None = None  # fuerza una fuente concreta si procede
    # Contexto para orientar la búsqueda en fuentes de texto libre (solo Tavily lo usa).
    search_context: str | None = None


@dataclass
class SearchHit:
    """Resultado individual devuelto por una fuente de búsqueda."""

    url: str
    source_name: str
    title: str | None = None
    snippet: str | None = None
    is_official: bool = False
    # Año de publicación identificado del resultado (R17 de investigador-v2); None = fecha
    # desconocida (no se descarta por antigüedad, pero el informe lo refleja).
    published_year: int | None = None


@dataclass
class FetchedDocument:
    """Documento leído en profundidad desde una URL."""

    url: str
    content_text: str
    title: str | None = None
    raw_bytes: bytes | None = None  # presente si el recurso era descargable
    content_type: str | None = None
    outbound_links: list[str] = field(default_factory=list)  # para profundización


# ---------------------------------------------------------------------------
# Tarea 4 — Modelos de dominio con verificación (Claim, GrantOpportunity)
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """Un dato factual con su estado de verificación, criticidad y procedencia.

    `value is None` => dato no encontrado. `is_critical` (p.ej. importe, plazo) marca los
    datos sujetos a revalidación por caducidad; `stale` indica que superó el umbral de
    frescura sin reconfirmarse.
    """

    field: str  # "importe" | "plazo" | "beneficiarios" | "titulo" | ...
    value: str | None = None
    status: VerificationStatus = VerificationStatus.NOT_FOUND
    is_critical: bool = False
    stale: bool = False
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class GrantOpportunity:
    """Una convocatoria de subvención; cada campo relevante es un `Claim` trazable."""

    title: Claim
    organism: Claim
    amount: Claim
    deadline: Claim
    scope: Claim
    url: Claim
    overall_status: VerificationStatus = VerificationStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# Tarea 5 — Registro persistente, captura y contenedores de entrada/salida
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    """Entrada PERSISTENTE del registro de fuentes consultadas.

    Acumula conocimiento entre investigaciones: `content_summary` resume la información útil
    hallada y se usa como PISTA en investigaciones futuras (nunca como dato definitivo);
    `topics` permite el recall por temática; `captured_at` gobierna la caducidad.
    """

    key: str  # URL normalizada o hash de la consulta
    kind: LedgerKind
    outcome: LedgerOutcome = "pending"
    content_summary: str = ""
    topics: list[str] = field(default_factory=list)
    source_ref: SourceRef | None = None
    captured_at: datetime = field(default_factory=_utcnow)


@dataclass
class StoredResource:
    """Material de entrenamiento capturado en local bajo RECURSOS/ENTRENAMIENTO/."""

    path: str
    source_url: str
    mode_of_capture: CaptureMode
    captured_at: datetime = field(default_factory=_utcnow)
    tags: list[str] = field(default_factory=list)


@dataclass
class Scope:
    """Ámbito de la investigación."""

    country: str | None = None
    eu: bool = False


@dataclass
class Filters:
    """Filtros opcionales de búsqueda de convocatorias."""

    min_amount: float | None = None
    deadline_after: date | None = None


@dataclass
class Unresolved:
    """Información que no se pudo resolver y para la que se pide ayuda al usuario."""

    topic: str  # campo o tema no resuelto
    reason: str
    help_needed: str


@dataclass
class FailedSource:
    """Fuente que falló durante la investigación (no aborta el resto)."""

    source_name: str
    error: str


@dataclass
class ResearchRequest:
    """Entrada pública de una investigación."""

    mode: ResearchMode
    query_terms: list[str] = field(default_factory=list)
    scope: Scope = field(default_factory=Scope)
    filters: Filters | None = None
    intent: Intent = "explore"  # gobierna la revalidación de datos críticos
    max_depth: int | None = None  # override de los límites de config
    max_pages: int | None = None
    # Orienta la búsqueda hacia un tipo de contenido (solo lo usa Tavily); p.ej.
    # "convocatoria subvención ONG 2026". Se propaga a cada SearchQuery en _derive_queries.
    search_context: str | None = None
    # Fuentes activas para esta investigación, por `source.name` (None = todas las
    # fuentes registradas). Lo usa la UI para activar/desactivar fuentes (R9).
    enabled_sources: set[str] | None = None
    # URLs aportadas por el usuario para lectura directa, aunque no haya hits de
    # búsqueda que las descubran (R9).
    direct_urls: list[str] = field(default_factory=list)


@dataclass
class ResearchReport:
    """Salida pública de una investigación, con trazabilidad y estado de verificación."""

    mode: ResearchMode
    opportunities: list[GrantOpportunity] = field(default_factory=list)  # modo calls
    resources: list[StoredResource] = field(default_factory=list)  # modo training
    ledger: list[LedgerEntry] = field(default_factory=list)  # fuentes consultadas
    reused_from_ledger: list[LedgerEntry] = field(default_factory=list)  # pistas reutilizadas
    unresolved: list[Unresolved] = field(default_factory=list)
    failed_sources: list[FailedSource] = field(default_factory=list)
