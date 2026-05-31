"""Tests de `InMemoryStore` (adaptador de persistencia en memoria).

Verifica el contrato del puerto `ResearchStore`: guardar/recuperar `LedgerEntry`, recall por
temática e índice de capturas (`has_url`/`add_resource`/`list_resources`). _Requirements: 5.3_
"""

import pytest

from agente_ong.research.models import LedgerEntry, StoredResource
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.store.memory import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def test_is_a_research_store(store: InMemoryStore) -> None:
    # Cumple el puerto y, a diferencia de la base abstracta, sí es instanciable.
    assert isinstance(store, ResearchStore)


# --- Ledger ---


def test_save_and_get_ledger_entry(store: InMemoryStore) -> None:
    entry = LedgerEntry(key="k1", kind="url", content_summary="resumen", topics=["cultura"])
    store.save_ledger_entry(entry)
    got = store.get_ledger_entry("k1")
    assert got is not None
    assert got.content_summary == "resumen"


def test_get_missing_ledger_entry_returns_none(store: InMemoryStore) -> None:
    assert store.get_ledger_entry("noexiste") is None


def test_save_ledger_entry_upserts_by_key(store: InMemoryStore) -> None:
    store.save_ledger_entry(LedgerEntry(key="k1", kind="url", content_summary="v1"))
    store.save_ledger_entry(LedgerEntry(key="k1", kind="url", content_summary="v2"))
    got = store.get_ledger_entry("k1")
    assert got is not None and got.content_summary == "v2"


# --- Recall por temática ---


def test_find_ledger_by_topic_matches_case_insensitive(store: InMemoryStore) -> None:
    store.save_ledger_entry(LedgerEntry(key="k1", kind="url", topics=["Cultura", "ONG"]))
    store.save_ledger_entry(LedgerEntry(key="k2", kind="query", topics=["Medioambiente"]))

    result = store.find_ledger_by_topic(["cultura"])
    assert [e.key for e in result] == ["k1"]


def test_find_ledger_by_topic_multiple_terms(store: InMemoryStore) -> None:
    store.save_ledger_entry(LedgerEntry(key="k1", kind="url", topics=["Cultura"]))
    store.save_ledger_entry(LedgerEntry(key="k2", kind="query", topics=["Medioambiente"]))

    result = store.find_ledger_by_topic(["CULTURA", "medioambiente"])
    assert {e.key for e in result} == {"k1", "k2"}


@pytest.mark.parametrize("terms", [[], ["inexistente"]])
def test_find_ledger_by_topic_no_match_returns_empty(store: InMemoryStore, terms) -> None:
    store.save_ledger_entry(LedgerEntry(key="k1", kind="url", topics=["cultura"]))
    assert store.find_ledger_by_topic(terms) == []


# --- Índice de capturas ---


def test_has_url_false_when_absent(store: InMemoryStore) -> None:
    assert store.has_url("https://x.es/a") is False


def test_add_resource_and_has_url_normalized(store: InMemoryStore) -> None:
    # source_url con mayúsculas y barra final: has_url lo detecta tras normalizar.
    store.add_resource(
        StoredResource(
            path="RECURSOS/ENTRENAMIENTO/a.pdf",
            source_url="HTTPS://X.es/a/",
            mode_of_capture="download",
        )
    )
    assert store.has_url("https://x.es/a") is True
    assert len(store.list_resources()) == 1


def test_list_resources_returns_defensive_copy(store: InMemoryStore) -> None:
    store.add_resource(
        StoredResource(path="p", source_url="https://x.es/a", mode_of_capture="text_copy")
    )
    store.list_resources().append("basura")  # type: ignore[arg-type]
    assert len(store.list_resources()) == 1
