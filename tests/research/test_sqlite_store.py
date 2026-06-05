"""Tests de `SqliteStore` (persistencia en SQLite, sin dependencias externas).

Usa una base de datos en archivo temporal (`tmp_path`): guardar/recuperar `LedgerEntry` con
`SourceRef`, `topics` y `captured_at`; upsert; recall por temática; índice de capturas; y
persistencia entre instancias (cerrar y reabrir el `.db`). _Requirements: 5.3_
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agente_ong.research.models import LedgerEntry, SourceRef, StoredResource
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.store.sqlite import SqliteStore

UTC = timezone.utc


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    # Subdirectorio inexistente: el store debe crearlo.
    return tmp_path / "data" / "agente_ong.db"


@pytest.fixture
def store(db_path: Path) -> SqliteStore:
    s = SqliteStore(db_path)
    yield s
    s.close()


def _entry(**kw) -> LedgerEntry:
    base = dict(key="https://x.es/a", kind="url", outcome="useful", topics=["cultura"])
    base.update(kw)
    return LedgerEntry(**base)


def test_is_a_research_store(store: SqliteStore) -> None:
    assert isinstance(store, ResearchStore)


def test_creates_db_file_and_parent_dir(db_path: Path) -> None:
    assert not db_path.exists()
    s = SqliteStore(db_path)
    assert db_path.exists()
    s.close()


# --- Ledger: guardar / recuperar con SourceRef y topics ---


def test_save_and_get_with_source_ref_and_topics(store: SqliteStore) -> None:
    ref = SourceRef(
        url="https://x.es/a",
        source_name="bdns",
        is_official=True,
        retrieved_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    store.save_ledger_entry(
        _entry(
            content_summary="resumen útil",
            topics=["Cultura", "ONG"],
            source_ref=ref,
            captured_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    )
    got = store.get_ledger_entry("https://x.es/a")
    assert got is not None
    assert got.content_summary == "resumen útil"
    assert got.topics == ["Cultura", "ONG"]  # orden estable
    assert got.captured_at == datetime(2026, 6, 2, tzinfo=UTC)
    assert got.source_ref is not None
    assert got.source_ref.source_name == "bdns"
    assert got.source_ref.is_official is True
    assert got.source_ref.retrieved_at == datetime(2026, 6, 1, tzinfo=UTC)


def test_get_missing_returns_none(store: SqliteStore) -> None:
    assert store.get_ledger_entry("noexiste") is None


def test_save_without_source_ref(store: SqliteStore) -> None:
    store.save_ledger_entry(_entry(source_ref=None))
    got = store.get_ledger_entry("https://x.es/a")
    assert got is not None and got.source_ref is None


def test_upsert_replaces_fields_and_topics(store: SqliteStore) -> None:
    ref = SourceRef(url="https://x.es/a", source_name="bdns", is_official=True)
    store.save_ledger_entry(_entry(content_summary="v1", topics=["cultura"], source_ref=ref))
    store.save_ledger_entry(
        _entry(content_summary="v2", outcome="empty", topics=["medioambiente"], source_ref=None)
    )
    got = store.get_ledger_entry("https://x.es/a")
    assert got is not None
    assert got.content_summary == "v2"
    assert got.outcome == "empty"
    assert got.topics == ["medioambiente"]  # los topics anteriores se reemplazan
    assert got.source_ref is None


# --- Recall por temática ---


def test_find_by_topic_is_case_insensitive(store: SqliteStore) -> None:
    store.save_ledger_entry(_entry(key="a", topics=["Cultura", "ONG"]))
    store.save_ledger_entry(_entry(key="b", kind="query", topics=["Medioambiente"]))

    assert [e.key for e in store.find_ledger_by_topic(["cultura"])] == ["a"]
    assert {e.key for e in store.find_ledger_by_topic(["CULTURA", "medioambiente"])} == {"a", "b"}


@pytest.mark.parametrize("terms", [[], ["inexistente"]])
def test_find_by_topic_no_match(store: SqliteStore, terms) -> None:
    store.save_ledger_entry(_entry(key="a", topics=["cultura"]))
    assert store.find_ledger_by_topic(terms) == []


# --- Índice de capturas ---


def test_has_url_and_add_resource_normalized(store: SqliteStore) -> None:
    assert store.has_url("https://r.es/p") is False
    store.add_resource(
        StoredResource(
            path="RECURSOS/ENTRENAMIENTO/p.pdf",
            source_url="HTTPS://R.es/p/",
            mode_of_capture="download",
            tags=["aprobado"],
        )
    )
    # URL equivalente (mayúsculas + barra final) detectada tras normalizar.
    assert store.has_url("https://r.es/p") is True
    resources = store.list_resources()
    assert len(resources) == 1
    assert resources[0].tags == ["aprobado"]
    assert resources[0].mode_of_capture == "download"


def test_add_resource_dedups_by_normalized_url(store: SqliteStore) -> None:
    store.add_resource(
        StoredResource(path="a.pdf", source_url="https://r.es/p", mode_of_capture="download")
    )
    store.add_resource(
        StoredResource(path="b.md", source_url="HTTPS://r.es/p/", mode_of_capture="text_copy")
    )
    resources = store.list_resources()
    assert len(resources) == 1  # misma URL normalizada -> upsert, no duplica
    assert resources[0].mode_of_capture == "text_copy"


# --- Persistencia entre instancias ---


def test_persists_across_instances(db_path: Path) -> None:
    first = SqliteStore(db_path)
    first.save_ledger_entry(_entry(content_summary="persistido", topics=["cultura"]))
    first.add_resource(
        StoredResource(path="p.pdf", source_url="https://r.es/p", mode_of_capture="download")
    )
    first.close()

    # Nueva instancia sobre el mismo archivo: los datos siguen ahí.
    second = SqliteStore(db_path)
    got = second.get_ledger_entry("https://x.es/a")
    assert got is not None and got.content_summary == "persistido"
    assert [e.key for e in second.find_ledger_by_topic(["cultura"])] == ["https://x.es/a"]
    assert second.has_url("https://r.es/p") is True
    assert len(second.list_resources()) == 1
    second.close()


def test_context_manager_closes(db_path: Path) -> None:
    with SqliteStore(db_path) as s:
        s.save_ledger_entry(_entry())
        assert s.get_ledger_entry("https://x.es/a") is not None
    # Tras salir del contexto, reabrir confirma que se persistió y cerró sin error.
    reopened = SqliteStore(db_path)
    assert reopened.get_ledger_entry("https://x.es/a") is not None
    reopened.close()
