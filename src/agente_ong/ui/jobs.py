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

from agente_ong.llm.config import LLMConfig, build_provider
from agente_ong.llm.enrichment import enrich_report
from agente_ong.llm.enrichment_serde import enriched_report_to_dict
from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import ResearchReport, ResearchRequest
from agente_ong.research.ods_catalogo import OdsEntry
from agente_ong.ui.models import Job, JobStatus, ResearchRun
from agente_ong.ui.project_store import ProjectStore

# Investigaciones simultáneas máximas (las demás esperan en cola del executor).
_DEFAULT_MAX_WORKERS = 2


class _RunsInvestigation(Protocol):
    """Contrato mínimo del investigador que ejecuta un job (lo cumple `Investigador`).

    `selected_ods` es obligatorio (R25, decisión B1): la UI exige multiselección de al
    menos 1 ODS (T26) antes de poder lanzar una investigación.
    """

    def run(self, request: ResearchRequest, selected_ods: list[OdsEntry]) -> ResearchReport: ...


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

    def submit(
        self,
        project_id: int,
        config: ResearchConfig,
        request: ResearchRequest,
        selected_ods: list[OdsEntry],
    ) -> str:
        """Encola una investigación y devuelve su `job_id` DE INMEDIATO (R2.1).

        El trabajo corre en un hilo de fondo con su propio `Investigador`; el estado se
        sigue con `status()`/`active_jobs()`. `selected_ods` (R25): ODS elegidos por el
        usuario en la UI, obligatorios (decisión B1, R25.3).
        """
        job_id = uuid.uuid4().hex
        job = Job(id=job_id, project_id=project_id, status="running")
        with self._lock:
            self._jobs[job_id] = job
        # El future se asigna tras registrar el job: el worker ya puede encontrarlo.
        job.future = self._executor.submit(
            self._run_job, job_id, config, request, selected_ods
        )
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

    def pop_finished(self) -> list[Job]:
        """Retira y devuelve los jobs terminados (done/error).

        La UI los recoge en un rerun para notificar; su resultado ya está persistido en
        `research_runs` (job.run_id), así que olvidarlos en memoria no pierde nada (R2.3).
        """
        with self._lock:
            finished = [job for job in self._jobs.values() if job.status != "running"]
            for job in finished:
                del self._jobs[job.id]
            return finished

    def shutdown(self, *, wait: bool = True) -> None:
        """Apaga el executor (tests/cierre de la app); no cancela lo ya en curso."""
        self._executor.shutdown(wait=wait)

    # --- Trabajo en el hilo de fondo (PROHIBIDO st.* aquí) ---

    def _run_job(
        self,
        job_id: str,
        config: ResearchConfig,
        request: ResearchRequest,
        selected_ods: list[OdsEntry],
    ) -> None:
        try:
            self._run_job_inner(job_id, config, request, selected_ods)
        except Exception:  # noqa: BLE001 - fallo del propio store: el job no queda colgado
            self._finish_job(job_id, "error")

    def _run_job_inner(
        self,
        job_id: str,
        config: ResearchConfig,
        request: ResearchRequest,
        selected_ods: list[OdsEntry],
    ) -> None:
        # Store PROPIO de este hilo (conexión SQLite por hilo), cerrado al salir.
        with ProjectStore(self._db_path) as store:
            project_id = self.get_job(job_id).project_id
            run_id = store.save_run(
                ResearchRun(project_id=project_id, params=_request_params(request))
            )
            with self._lock:
                self._jobs[job_id].run_id = run_id
            try:
                with self._factory(config) as investigador:
                    report = investigador.run(request, selected_ods)
            except Exception as exc:  # noqa: BLE001 - aislar el fallo, no tumbar otros jobs
                store.update_run_status(run_id, "error", error=str(exc))
                self._finish_job(job_id, "error")
                return
            provider = build_provider(LLMConfig.from_env())
            enriched = enrich_report(report, provider)
            store.update_run_status(run_id, "done", report=enriched_report_to_dict(enriched))
            self._finish_job(job_id, "done")

    def _finish_job(self, job_id: str, status: JobStatus) -> None:
        """Cierra el job en memoria; el resultado ya quedó persistido en research_runs."""
        with self._lock:
            self._jobs[job_id].status = status


def _request_params(request: ResearchRequest) -> dict:
    """Parámetros del lanzamiento que se guardan junto al run (trazabilidad, R12.5)."""
    return {
        "query_terms": list(request.query_terms),
        "max_depth": request.max_depth,
        "max_pages": request.max_pages,
        "enabled_sources": (
            sorted(request.enabled_sources) if request.enabled_sources is not None else None
        ),
        "direct_urls": list(request.direct_urls),
        "search_context": request.search_context,
    }
