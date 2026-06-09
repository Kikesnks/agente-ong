"""Tests de `ProjectStore` (`ui/project_store.py`).

CRUD de proyectos, unicidad de nombre, borrado en cascada de runs, ciclo de vida de una
investigación (save → update_run_status) y round-trip del informe serializado en
`report_json`. _Requirements: 12.2, 12.5, 6.2_
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport, VerificationStatus
from agente_ong.ui.models import ResearchRun
from agente_ong.ui.project_store import ProjectStore
from agente_ong.ui.report_serde import report_from_dict, report_to_dict


@pytest.fixture
def store(tmp_path: Path):
    with ProjectStore(tmp_path / "agente_ong.db") as ps:
        yield ps


# --- Proyectos (R12.2/R12.3, R1.2) ---


def test_create_and_get_project_round_trip(store: ProjectStore) -> None:
    created = store.create_project("Mi ONG", "Conseguir fondos", ["cultura", "salud mental"])
    assert created.id is not None

    loaded = store.get_project(created.id)
    assert loaded is not None
    assert loaded.name == "Mi ONG"
    assert loaded.objective == "Conseguir fondos"
    assert loaded.search_terms == ["cultura", "salud mental"]
    assert loaded.created_at == created.created_at


def test_list_projects_returns_all(store: ProjectStore) -> None:
    store.create_project("A")
    store.create_project("B")
    assert {p.name for p in store.list_projects()} == {"A", "B"}


def test_get_project_missing_returns_none(store: ProjectStore) -> None:
    assert store.get_project(999) is None


def test_duplicate_name_raises_integrity_error(store: ProjectStore) -> None:
    store.create_project("Única")
    with pytest.raises(sqlite3.IntegrityError):
        store.create_project("Única")


def test_empty_name_is_rejected(store: ProjectStore) -> None:
    with pytest.raises(ValueError):
        store.create_project("   ")


# --- Runs (R12.5/R12.6) ---


def _sample_report_dict() -> dict:
    claim = Claim(field="titulo", value="Ayudas", status=VerificationStatus.VERIFIED)
    opp = GrantOpportunity(
        title=claim,
        organism=Claim(field="organismo"),
        amount=Claim(field="importe", is_critical=True),
        deadline=Claim(field="plazo", is_critical=True),
        scope=Claim(field="ambito"),
        url=Claim(field="url", value="https://bo.es/c1"),
        overall_status=VerificationStatus.VERIFIED,
    )
    return report_to_dict(ResearchReport(mode="calls", opportunities=[opp]))


def test_run_lifecycle_save_then_done_with_report(store: ProjectStore) -> None:
    project = store.create_project("ONG")
    run_id = store.save_run(ResearchRun(project_id=project.id, params={"depth": "normal"}))

    store.update_run_status(run_id, "done", report=_sample_report_dict())

    loaded = store.get_run(run_id)
    assert loaded.status == "done"
    assert loaded.finished_at is not None
    assert loaded.error is None
    assert loaded.params == {"depth": "normal"}
    # Round-trip completo: el informe guardado se reconstruye fiel (R6.2).
    restored = report_from_dict(loaded.report)
    assert restored.opportunities[0].title.status is VerificationStatus.VERIFIED
    assert restored.opportunities[0].title.value == "Ayudas"


def test_run_lifecycle_error_keeps_message(store: ProjectStore) -> None:
    project = store.create_project("ONG")
    run_id = store.save_run(ResearchRun(project_id=project.id))

    store.update_run_status(run_id, "error", error="fallo de red")

    loaded = store.get_run(run_id)
    assert loaded.status == "error"
    assert loaded.error == "fallo de red"
    assert loaded.report is None
    assert loaded.finished_at is not None


def test_list_runs_filters_by_project(store: ProjectStore) -> None:
    p1 = store.create_project("Uno")
    p2 = store.create_project("Dos")
    store.save_run(ResearchRun(project_id=p1.id))
    store.save_run(ResearchRun(project_id=p1.id))
    store.save_run(ResearchRun(project_id=p2.id))

    assert len(store.list_runs(p1.id)) == 2
    assert len(store.list_runs(p2.id)) == 1


def test_deleting_project_cascades_to_runs(store: ProjectStore) -> None:
    project = store.create_project("Efímero")
    run_id = store.save_run(ResearchRun(project_id=project.id))

    # Borrado directo en SQL (la UI no expone delete_project todavía): debe arrastrar los runs.
    with store._conn:  # noqa: SLF001 - acceso de test al detalle de persistencia
        store._conn.execute("DELETE FROM projects WHERE id=?", (project.id,))

    assert store.get_run(run_id) is None
    assert store.list_runs(project.id) == []
