"""Adaptador de persistencia en SQLite.

`SqliteStore` implementa `ResearchStore` sobre una base de datos SQLite usando el módulo
`sqlite3` de la biblioteca estándar (cero dependencias externas). Es la persistencia REAL del
producto: el registro de fuentes (`SourceLedger`) y el índice de capturas sobreviven entre
sesiones en un único archivo `.db` que viaja con la app, sin servicios externos.

Diseño (ver plan aprobado en la spec):
  - `ledger_entries`: una fila por entrada; la `SourceRef` (0..1 por entrada) va aplanada.
  - `ledger_topics`: topics normalizados a tabla aparte PORQUE se buscan (`find_ledger_by_topic`);
    columna `topic_lc` indexada para match insensible a mayúsculas.
  - `resources`: índice de capturas; `source_url_norm` UNIQUE para `has_url` O(1) y dedup; los
    tags van como JSON (no se buscan, no merecen tabla).

Detalles SQLite:
  - WAL (`journal_mode=WAL`) para durabilidad y lecturas concurrentes (crea sidecars -wal/-shm).
  - `foreign_keys=ON` (en SQLite están OFF por defecto) para el ON DELETE CASCADE de topics.
  - TODAS las consultas son parametrizadas (`?`): el contenido proviene de webs scrapeadas
    (URLs, summaries, topics) -> nunca interpolar en el SQL (prevención de inyección).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType

from agente_ong.research.models import LedgerEntry, SourceRef, StoredResource
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.urlnorm import normalize_url

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_entries (
    key                 TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    outcome             TEXT NOT NULL,
    content_summary     TEXT NOT NULL DEFAULT '',
    captured_at         TEXT NOT NULL,
    source_url          TEXT,
    source_name         TEXT,
    source_is_official  INTEGER,
    source_retrieved_at TEXT
);

CREATE TABLE IF NOT EXISTS ledger_topics (
    entry_key TEXT NOT NULL REFERENCES ledger_entries(key) ON DELETE CASCADE,
    topic     TEXT NOT NULL,
    topic_lc  TEXT NOT NULL,
    PRIMARY KEY (entry_key, topic)
);
CREATE INDEX IF NOT EXISTS idx_ledger_topics_lc ON ledger_topics(topic_lc);

CREATE TABLE IF NOT EXISTS resources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    source_url_norm TEXT NOT NULL UNIQUE,
    mode_of_capture TEXT NOT NULL,
    captured_at     TEXT NOT NULL,
    tags_json       TEXT NOT NULL DEFAULT '[]'
);
"""


class SqliteStore(ResearchStore):
    """Implementación de `ResearchStore` respaldada por SQLite (stdlib, sin dependencias)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        if self._db_path.parent and not self._db_path.parent.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # --- Ciclo de vida / context manager ---

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # --- Ledger ---

    def save_ledger_entry(self, entry: LedgerEntry) -> None:
        ref = entry.source_ref
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO ledger_entries
                    (key, kind, outcome, content_summary, captured_at,
                     source_url, source_name, source_is_official, source_retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    kind=excluded.kind,
                    outcome=excluded.outcome,
                    content_summary=excluded.content_summary,
                    captured_at=excluded.captured_at,
                    source_url=excluded.source_url,
                    source_name=excluded.source_name,
                    source_is_official=excluded.source_is_official,
                    source_retrieved_at=excluded.source_retrieved_at
                """,
                (
                    entry.key,
                    entry.kind,
                    entry.outcome,
                    entry.content_summary,
                    entry.captured_at.isoformat(),
                    ref.url if ref else None,
                    ref.source_name if ref else None,
                    int(ref.is_official) if ref else None,
                    ref.retrieved_at.isoformat() if ref else None,
                ),
            )
            # Topics: se borran y reinsertan (upsert simple) dentro de la misma transacción.
            self._conn.execute("DELETE FROM ledger_topics WHERE entry_key=?", (entry.key,))
            self._conn.executemany(
                "INSERT INTO ledger_topics (entry_key, topic, topic_lc) VALUES (?, ?, ?)",
                [(entry.key, topic, topic.lower()) for topic in entry.topics],
            )

    def get_ledger_entry(self, key: str) -> LedgerEntry | None:
        row = self._conn.execute(
            "SELECT * FROM ledger_entries WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_ledger_entry(row)

    def find_ledger_by_topic(self, terms: list[str]) -> list[LedgerEntry]:
        wanted = [t.lower() for t in terms if t]
        if not wanted:
            return []
        placeholders = ",".join("?" * len(wanted))
        rows = self._conn.execute(
            f"""
            SELECT e.* FROM ledger_entries e
            WHERE e.key IN (
                SELECT DISTINCT entry_key FROM ledger_topics WHERE topic_lc IN ({placeholders})
            )
            ORDER BY e.rowid
            """,
            wanted,
        ).fetchall()
        return [self._row_to_ledger_entry(row) for row in rows]

    # --- Índice de capturas ---

    def has_url(self, url: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM resources WHERE source_url_norm=? LIMIT 1", (normalize_url(url),)
        ).fetchone()
        return row is not None

    def add_resource(self, resource: StoredResource) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO resources
                    (path, source_url, source_url_norm, mode_of_capture, captured_at, tags_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_url_norm) DO UPDATE SET
                    path=excluded.path,
                    source_url=excluded.source_url,
                    mode_of_capture=excluded.mode_of_capture,
                    captured_at=excluded.captured_at,
                    tags_json=excluded.tags_json
                """,
                (
                    resource.path,
                    resource.source_url,
                    normalize_url(resource.source_url),
                    resource.mode_of_capture,
                    resource.captured_at.isoformat(),
                    json.dumps(resource.tags),
                ),
            )

    def list_resources(self) -> list[StoredResource]:
        rows = self._conn.execute("SELECT * FROM resources ORDER BY id").fetchall()
        return [
            StoredResource(
                path=row["path"],
                source_url=row["source_url"],
                mode_of_capture=row["mode_of_capture"],
                captured_at=datetime.fromisoformat(row["captured_at"]),
                tags=list(json.loads(row["tags_json"])),
            )
            for row in rows
        ]

    # --- Helpers ---

    def _row_to_ledger_entry(self, row: sqlite3.Row) -> LedgerEntry:
        source_ref = None
        if row["source_url"] is not None:
            source_ref = SourceRef(
                url=row["source_url"],
                source_name=row["source_name"],
                is_official=bool(row["source_is_official"]),
                retrieved_at=datetime.fromisoformat(row["source_retrieved_at"]),
            )
        return LedgerEntry(
            key=row["key"],
            kind=row["kind"],
            outcome=row["outcome"],
            content_summary=row["content_summary"],
            topics=self._load_topics(row["key"]),
            source_ref=source_ref,
            captured_at=datetime.fromisoformat(row["captured_at"]),
        )

    def _load_topics(self, entry_key: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT topic FROM ledger_topics WHERE entry_key=? ORDER BY topic", (entry_key,)
        ).fetchall()
        return [row["topic"] for row in rows]
