"""Tests de `SourceLedger` (registro de fuentes, persistente entre investigaciones).

Cubre la no-repetición con normalización de claves, el recall de pistas previas vía store, y
la persistencia/rehidratación con `flush`. _Requirements: 5.1, 5.2, 5.3_
"""

import pytest

from agente_ong.research.ledger import SourceLedger, _canonical_key
from agente_ong.research.models import SourceRef
from agente_ong.research.store.memory import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def ledger(store: InMemoryStore) -> SourceLedger:
    return SourceLedger(store)


# --- No repetir (vista en memoria, con normalización) ---


def test_unseen_then_seen_after_mark(ledger: SourceLedger) -> None:
    assert ledger.seen("https://x.es/a") is False
    ledger.mark_queried("https://x.es/a")
    assert ledger.seen("https://x.es/a") is True


def test_equivalent_urls_share_key(ledger: SourceLedger) -> None:
    # Mayúsculas + barra final: la URL se normaliza, así que cuenta como la misma.
    ledger.mark_queried("HTTPS://X.es/a/")
    assert ledger.seen("https://x.es/a") is True


def test_query_keys_are_hashed_and_distinct_from_urls(ledger: SourceLedger) -> None:
    assert _canonical_key("subvenciones cultura", "query").startswith("query:")
    ledger.mark_queried("subvenciones cultura", kind="query")
    assert ledger.seen("subvenciones cultura", kind="query") is True
    assert ledger.seen("otra consulta", kind="query") is False


# --- Registrar resultado ---


def test_record_stores_summary_and_topics(ledger: SourceLedger) -> None:
    sr = SourceRef(url="https://x.es/a", source_name="firecrawl", is_official=False)
    entry = ledger.record(
        "https://x.es/a",
        kind="url",
        outcome="useful",
        content_summary="resumen útil",
        topics=["cultura"],
        source_ref=sr,
    )
    assert entry.outcome == "useful"
    assert entry.content_summary == "resumen útil"
    assert entry.topics == ["cultura"]
    assert entry.captured_at is not None
    assert ledger.seen("https://x.es/a") is True


# --- Persistencia y recall entre investigaciones ---


def test_flush_persists_to_store(ledger: SourceLedger, store: InMemoryStore) -> None:
    ledger.record(
        "https://x.es/a", kind="url", outcome="useful", content_summary="r", topics=["cultura"]
    )
    ledger.flush()
    key = _canonical_key("https://x.es/a", "url")
    persisted = store.get_ledger_entry(key)
    assert persisted is not None and persisted.content_summary == "r"


def test_recall_returns_previous_hint_from_store(store: InMemoryStore) -> None:
    # Investigación 1: registra y persiste.
    first = SourceLedger(store)
    first.record(
        "https://x.es/a", kind="url", outcome="useful", content_summary="r", topics=["cultura"]
    )
    first.flush()

    # Investigación 2 (ledger nuevo, mismo store): recupera la pista por temática.
    second = SourceLedger(store)
    hints = second.find_by_topic(["cultura"])
    assert [h.key for h in hints] == [_canonical_key("https://x.es/a", "url")]


def test_recall_does_not_mark_hint_as_seen(store: InMemoryStore) -> None:
    first = SourceLedger(store)
    first.record("https://x.es/a", kind="url", outcome="useful", topics=["cultura"])
    first.flush()

    second = SourceLedger(store)
    second.find_by_topic(["cultura"])
    # La pista puede revisitarse para revalidación: NO debe quedar marcada como vista.
    assert second.seen("https://x.es/a") is False


def test_find_by_topic_no_terms_returns_empty(ledger: SourceLedger) -> None:
    ledger.record("https://x.es/a", kind="url", outcome="useful", topics=["cultura"])
    assert ledger.find_by_topic([]) == []


def test_entries_lists_current_investigation(ledger: SourceLedger) -> None:
    ledger.mark_queried("https://x.es/a")
    ledger.mark_queried("https://x.es/b")
    keys = {e.key for e in ledger.entries()}
    assert keys == {_canonical_key("https://x.es/a", "url"), _canonical_key("https://x.es/b", "url")}
