"""Tests del `JobManager` (`ui/jobs.py`) con un Investigador fake inyectable.

Ciclo de vida completo: submit → done persistido con informe y params; excepción del
investigador → error persistido sin afectar a otros jobs; pop_finished retira los
terminados. _Requirements: 2.1, 2.3, 2.4_
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import ResearchReport, ResearchRequest
from agente_ong.ui.jobs import JobManager
from agente_ong.ui.project_store import ProjectStore
from agente_ong.ui.report_serde import report_from_dict

_TIMEOUT = 10  # segundos; los fakes terminan en milisegundos


class FakeInvestigador:
    """Doble del `Investigador`: context manager con `run()` configurable."""

    def __init__(
        self,
        *,
        report: ResearchReport | None = None,
        fail: Exception | None = None,
        release: threading.Event | None = None,
    ) -> None:
        self._report = report or ResearchReport(mode="calls")
        self._fail = fail
        self._release = release  # permite mantener el job "en curso" hasta liberarlo
        self.ran_in_thread: str | None = None

    def __enter__(self) -> "FakeInvestigador":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def run(self, request: ResearchRequest) -> ResearchReport:
        self.ran_in_thread = threading.current_thread().name
        if self._release is not None:
            assert self._release.wait(_TIMEOUT), "el test no liberó el job"
        if self._fail is not None:
            raise self._fail
        return self._report


def _wait(manager: JobManager, job_id: str) -> None:
    manager.get_job(job_id).future.result(timeout=_TIMEOUT)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agente_ong.db"


@pytest.fixture
def project_id(db_path: Path) -> int:
    with ProjectStore(db_path) as store:
        return store.create_project("ONG").id


def _request(**kw) -> ResearchRequest:
    kw.setdefault("mode", "calls")
    return ResearchRequest(**kw)


def _config() -> ResearchConfig:
    return ResearchConfig(db_path=None)


# --- Ciclo feliz: submit → done persistido (R2.1, R2.3) ---


def test_submit_returns_immediately_and_persists_done_run(db_path: Path, project_id: int) -> None:
    release = threading.Event()
    fake = FakeInvestigador(release=release)
    manager = JobManager(db_path, investigador_factory=lambda cfg: fake)
    try:
        job_id = manager.submit(
            project_id, _config(), _request(query_terms=["cultura"], max_depth=1)
        )
        # submit no bloquea: el job sigue corriendo hasta que el test lo libere.
        assert manager.status(job_id) == "running"
        assert [j.id for j in manager.active_jobs()] == [job_id]

        release.set()
        _wait(manager, job_id)

        assert manager.status(job_id) == "done"
        assert fake.ran_in_thread != threading.main_thread().name, "debe correr en hilo de fondo"

        with ProjectStore(db_path) as store:
            runs = store.list_runs(project_id)
            assert len(runs) == 1
            run = runs[0]
            assert run.id == manager.get_job(job_id).run_id
            assert run.status == "done" and run.finished_at is not None
            assert report_from_dict(run.report).mode == "calls"
            assert run.params["query_terms"] == ["cultura"]
            assert run.params["max_depth"] == 1
    finally:
        manager.shutdown()


# --- Fallo aislado: error persistido, otros jobs intactos (R2.4) ---


def test_failing_job_persists_error_and_does_not_affect_others(
    db_path: Path, project_id: int
) -> None:
    fakes = {
        "ok": FakeInvestigador(),
        "ko": FakeInvestigador(fail=RuntimeError("fallo simulado")),
    }
    order: list[str] = ["ko", "ok"]
    manager = JobManager(
        db_path, investigador_factory=lambda cfg: fakes[order.pop(0)]
    )
    try:
        bad_id = manager.submit(project_id, _config(), _request())
        _wait(manager, bad_id)
        good_id = manager.submit(project_id, _config(), _request())
        _wait(manager, good_id)

        assert manager.status(bad_id) == "error"
        assert manager.status(good_id) == "done"

        with ProjectStore(db_path) as store:
            by_id = {run.id: run for run in store.list_runs(project_id)}
            bad_run = by_id[manager.get_job(bad_id).run_id]
            good_run = by_id[manager.get_job(good_id).run_id]
            assert bad_run.status == "error" and bad_run.error == "fallo simulado"
            assert bad_run.report is None
            assert good_run.status == "done" and good_run.error is None
    finally:
        manager.shutdown()


# --- pop_finished retira los terminados y conserva los activos ---


def test_pop_finished_removes_only_completed_jobs(db_path: Path, project_id: int) -> None:
    release = threading.Event()
    fakes = [FakeInvestigador(), FakeInvestigador(release=release)]
    manager = JobManager(db_path, investigador_factory=lambda cfg: fakes.pop(0))
    try:
        done_id = manager.submit(project_id, _config(), _request())
        _wait(manager, done_id)
        slow_id = manager.submit(project_id, _config(), _request())

        finished = manager.pop_finished()
        assert [j.id for j in finished] == [done_id]
        assert finished[0].run_id is not None
        assert manager.get_job(done_id) is None, "el terminado se retira"
        assert manager.status(slow_id) == "running", "el activo permanece"

        release.set()
        _wait(manager, slow_id)
        assert [j.id for j in manager.pop_finished()] == [slow_id]
    finally:
        manager.shutdown()
