"""Ejecución asíncrona de investigaciones (`JobManager`, R2).

Ejecuta cada investigación en un hilo de fondo (`ThreadPoolExecutor`) para no bloquear la
UI; el estado se consulta de forma thread-safe (`threading.Lock`) desde el hilo de script.

Reglas duras (design.md):
  - Los hilos de fondo NUNCA llaman a `st.*` (no tienen ScriptRunContext): solo computan y
    escriben en las estructuras de este módulo y en SQLite.
  - Conexión SQLite POR HILO: cada worker abre su PROPIO `Investigador` (y, al persistir, su
    propio `ProjectStore`); nada de compartir conexiones con el hilo de la UI.
  - El fallo de un job se captura y aísla: no tumba ni la app ni los demás jobs (R2.4).

`investigador_factory` permite inyectar un Investigador fake en los tests (UI-26), igual
que `Investigador` admite fuentes inyectadas.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, ContextManager, Protocol

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import ResearchReport, ResearchRequest
from agente_ong.ui.models import Job, JobStatus

# Investigaciones simultáneas máximas (las demás esperan en cola del executor).
_DEFAULT_MAX_WORKERS = 2


class _RunsInvestigation(Protocol):
    """Contrato mínimo del investigador que ejecuta un job (lo cumple `Investigador`)."""

    def run(self, request: ResearchRequest) -> ResearchReport: ...


# La factoría recibe la config del job y devuelve un investigador usable como context
# manager (el real cierra su conexión SQLite al salir).
InvestigadorFactory = Callable[[ResearchConfig], ContextManager[_RunsInvestigation]]


def _default_factory(config: ResearchConfig) -> ContextManager[_RunsInvestigation]:
    # Import perezoso: no cargar el grafo/fuentes al importar la capa de jobs.
    from agente_ong.research.investigador import Investigador

    return Investigador(config)


class JobManager:
    """Lanza investigaciones en segundo plano y expone su estado de forma thread-safe.

    En la app vive como singleton de proceso (vía `st.cache_resource`) para sobrevivir a
    los reruns de Streamlit.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        max_workers: int = _DEFAULT_MAX_WORKERS,
        investigador_factory: InvestigadorFactory | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._factory = investigador_factory or _default_factory
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="research-job"
        )
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    # --- API del hilo de script (UI) ---

    def submit(self, project_id: int, config: ResearchConfig, request: ResearchRequest) -> str:
        """Encola una investigación y devuelve su `job_id` DE INMEDIATO (R2.1).

        El trabajo corre en un hilo de fondo con su propio `Investigador`; el estado se
        sigue con `status()`/`active_jobs()`.
        """
        job_id = uuid.uuid4().hex
        job = Job(id=job_id, project_id=project_id, status="running")
        with self._lock:
            self._jobs[job_id] = job
        # El future se asigna tras registrar el job: el worker ya puede encontrarlo.
        job.future = self._executor.submit(self._run_job, job_id, config, request)
        return job_id

    def status(self, job_id: str) -> JobStatus:
        """Estado actual del job; un id desconocido lanza `KeyError`."""
        with self._lock:
            return self._jobs[job_id].status

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_jobs(self) -> list[Job]:
        """Jobs aún en ejecución (para decidir si la UI sigue refrescando, R2.2)."""
        with self._lock:
            return [job for job in self._jobs.values() if job.status == "running"]

    def shutdown(self, *, wait: bool = True) -> None:
        """Apaga el executor (tests/cierre de la app); no cancela lo ya en curso."""
        self._executor.shutdown(wait=wait)

    # --- Trabajo en el hilo de fondo (PROHIBIDO st.* aquí) ---

    def _run_job(self, job_id: str, config: ResearchConfig, request: ResearchRequest) -> None:
        try:
            with self._factory(config) as investigador:
                report = investigador.run(request)
        except Exception as exc:  # noqa: BLE001 - aislar el fallo, no tumbar otros jobs
            self._finish_job(job_id, "error", error=str(exc))
            return
        self._finish_job(job_id, "done", report=report)

    def _finish_job(
        self,
        job_id: str,
        status: JobStatus,
        *,
        report: ResearchReport | None = None,
        error: str | None = None,
    ) -> None:
        """Cierra el job en memoria (la persistencia del run se añade en la tarea 25)."""
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
