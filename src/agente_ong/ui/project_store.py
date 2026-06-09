"""Persistencia de proyectos e investigaciones de la capa de UI (`ProjectStore`).

Gestiona las tablas `projects` y `research_runs` en el MISMO archivo `.db` del producto
(`config.db_path`), sin tocar las tablas del investigador (que sigue dueño de las suyas).
Sigue el patrón de `SqliteStore` (research/store/sqlite.py): WAL, `foreign_keys=ON` y todas
las consultas parametrizadas.

Regla de hilos (ver design.md): las conexiones sqlite3 son por hilo. Cada hilo (el de script
de Streamlit y cada worker de fondo) abre su PROPIO `ProjectStore`; nunca se comparte una
instancia entre hilos.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType

from agente_ong.ui.models import Project

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    objective    TEXT NOT NULL DEFAULT '',
    terms_json   TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    finished_at  TEXT,
    params_json  TEXT NOT NULL DEFAULT '{}',
    report_json  TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON research_runs(project_id);
"""


class ProjectStore:
    """CRUD de proyectos e historial de investigaciones sobre SQLite (stdlib)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        if self._db_path.parent and not self._db_path.parent.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # --- Ciclo de vida / context manager ---

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ProjectStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # --- Proyectos ---

    def create_project(self, name: str, objective: str = "", search_terms: list[str] | None = None) -> Project:
        """Crea un proyecto y devuelve el `Project` persistido (con id).

        El nombre debe ser no vacío; la unicidad la garantiza `UNIQUE(name)` (R1.4/R12.3):
        un duplicado lanza `sqlite3.IntegrityError`, que la UI traduce a mensaje claro.
        """
        clean = (name or "").strip()
        if not clean:
            raise ValueError("El nombre del proyecto no puede estar vacío.")
        project = Project(name=clean, objective=objective, search_terms=list(search_terms or []))
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO projects (name, objective, terms_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    project.name,
                    project.objective,
                    json.dumps(project.search_terms),
                    project.created_at.isoformat(),
                ),
            )
        project.id = cursor.lastrowid
        return project

    def list_projects(self) -> list[Project]:
        """Todos los proyectos, más recientes primero (para la sidebar)."""
        rows = self._conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [self._row_to_project(row) for row in rows]

    def get_project(self, project_id: int) -> Project | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        return self._row_to_project(row) if row else None

    # --- Helpers ---

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            objective=row["objective"],
            search_terms=list(json.loads(row["terms_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
