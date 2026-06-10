"""Modelos de la capa de UI.

Tipos propios de la interfaz: `Project` (proyecto de la ONG), `ResearchRun` (una
investigación asociada a un proyecto, persistida en SQLite) y `Job` (trabajo en curso en un
hilo de fondo; vive solo en memoria). Los informes (`ResearchReport`) son del dominio del
investigador y aquí solo se referencian ya serializados (`report` como dict, vía
`report_serde`).
"""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

# --- Alias de tipos cerrados (Literals) ---
# Estados de una investigación persistida y de un job en memoria (mismo ciclo de vida).
RunStatus = Literal["running", "done", "error"]
JobStatus = Literal["running", "done", "error"]


def _utcnow() -> datetime:
    """Marca temporal actual con zona UTC (para created_at)."""
    return datetime.now(timezone.utc)


@dataclass
class Project:
    """Proyecto de la ONG: agrupa objetivo, términos de búsqueda e investigaciones.

    `id is None` => aún no persistido. `name` es único y debe ser válido como nombre de
    carpeta (gobierna `RECURSOS/[name]/`). `search_context` (R13) describe el tipo de
    organización y su ámbito en lenguaje no técnico; lo heredan todas las investigaciones
    del proyecto ("" => default de `request_builder` en el lanzamiento).
    """

    name: str
    objective: str = ""
    search_terms: list[str] = field(default_factory=list)
    search_context: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class ResearchRun:
    """Una investigación de un proyecto, con sus parámetros e informe serializados.

    `params` registra los controles con que se lanzó (profundidad, fuentes, año, URLs);
    `report` es el `ResearchReport` serializado a dict cuando `status == "done"`; `error`
    lleva el mensaje cuando `status == "error"`.
    """

    project_id: int
    status: RunStatus = "running"
    id: int | None = None
    created_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None
    params: dict = field(default_factory=dict)
    report: dict | None = None
    error: str | None = None


@dataclass
class Job:
    """Trabajo de investigación en curso (en memoria, no persistente).

    `future` es el handle del hilo de fondo; `run_id` enlaza con la fila de
    `research_runs` una vez persistido el resultado.
    """

    id: str
    project_id: int
    status: JobStatus = "running"
    future: Future | None = None
    run_id: int | None = None
