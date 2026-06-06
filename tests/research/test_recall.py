"""Test de integración del recall entre investigaciones (persistencia real con SQLite).

Valida que el conocimiento se acumula entre investigaciones distintas sobre la misma base de
datos: una primera `run` persiste el ledger; una segunda `run` (otra instancia de
`Investigador`, mismo `.db`) recupera esas entradas como PISTAS (`reused_from_ledger`) sin
marcarlas como vistas, y los datos críticos caducados recuperados del store fuerzan
revalidación (`stale`). _Requirements: 4.1, 5.3_
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.investigador import Investigador
from agente_ong.research.models import Claim, LedgerEntry, ResearchRequest, SourceRef
from agente_ong.research.store.sqlite import SqliteStore
from agente_ong.research.urlnorm import normalize_url
from agente_ong.research.verification import VerificationPolicy
from fakes import FakeFetchSource, FakeSearchSource, make_document, make_hit

UTC = timezone.utc
C1 = "https://bo.es/c1"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agente_ong.db"


def _sources():
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[make_hit(C1, source_name="bdns", title="Conv 1", is_official=True)],
    )
    fetch = FakeFetchSource(documents={C1: make_document(C1, text="detalle relevante de la convocatoria")})
    return bdns, fetch


def _request() -> ResearchRequest:
    return ResearchRequest(mode="calls", query_terms=["cultura"])


# --- Recall entre investigaciones (Requirement 5.3) ---


def test_ledger_persists_and_is_recalled_in_next_investigation(db_path: Path) -> None:
    config = ResearchConfig(max_depth=1, db_path=db_path)

    # Investigación 1: no hay pistas previas; persiste el ledger al cerrar.
    bdns1, fetch1 = _sources()
    with Investigador(config, sources=[bdns1, fetch1]) as inv1:
        report1 = inv1.run(_request())
    assert report1.reused_from_ledger == []

    # Investigación 2: instancia nueva sobre el MISMO .db -> recall de la pista previa.
    bdns2, fetch2 = _sources()
    with Investigador(config, sources=[bdns2, fetch2]) as inv2:
        report2 = inv2.run(_request())

    keys = [e.key for e in report2.reused_from_ledger]
    assert normalize_url(C1) in keys
    # La pista trae el resumen persistido de la investigación anterior.
    hint = next(e for e in report2.reused_from_ledger if e.key == normalize_url(C1))
    assert hint.content_summary  # resumen no vacío, recuperado del .db


def test_recalled_hint_is_revisited_not_skipped(db_path: Path) -> None:
    config = ResearchConfig(max_depth=1, db_path=db_path)

    bdns1, fetch1 = _sources()
    with Investigador(config, sources=[bdns1, fetch1]) as inv1:
        inv1.run(_request())

    # En la segunda investigación la pista NO se marca como vista: se vuelve a leer la URL.
    bdns2, fetch2 = _sources()
    with Investigador(config, sources=[bdns2, fetch2]) as inv2:
        report2 = inv2.run(_request())

    assert C1 in fetch2.fetch_calls  # se revisitó (revalidable), no se omitió
    assert len(report2.opportunities) == 1


# --- Persistencia real del store entre instancias ---


def test_ledger_entry_survives_close_and_reopen(db_path: Path) -> None:
    config = ResearchConfig(max_depth=1, db_path=db_path)
    bdns1, fetch1 = _sources()
    with Investigador(config, sources=[bdns1, fetch1]) as inv1:
        inv1.run(_request())

    # Reabrir el store directamente y comprobar que la entrada del ledger sigue ahí.
    store = SqliteStore(db_path)
    entry = store.get_ledger_entry(normalize_url(C1))
    store.close()
    assert entry is not None
    assert entry.topics == ["cultura"]
    assert entry.source_ref is not None and entry.source_ref.source_name == "fake-fetch"


# --- Revalidación de datos críticos caducados recuperados del store (Requirement 4.1) ---


def test_stale_recalled_critical_data_triggers_revalidation(db_path: Path) -> None:
    old = datetime.now(UTC) - timedelta(days=400)

    # Sembrar una entrada "antigua" en el store persistente (como de una investigación pasada).
    store = SqliteStore(db_path)
    ref = SourceRef(url=C1, source_name="bdns", is_official=True, retrieved_at=old)
    store.save_ledger_entry(
        LedgerEntry(
            key=normalize_url(C1),
            kind="url",
            outcome="useful",
            content_summary="importe estimado 50000 EUR",
            topics=["cultura"],
            source_ref=ref,
            captured_at=old,
        )
    )
    store.close()

    # Recuperarla en otra instancia: las fechas sobreviven el viaje por SQLite.
    reopened = SqliteStore(db_path)
    hints = reopened.find_ledger_by_topic(["cultura"])
    reopened.close()
    assert len(hints) == 1
    hint = hints[0]
    assert hint.source_ref is not None and hint.source_ref.retrieved_at == old

    # Un dato crítico apoyado solo por esa pista caducada exige revalidación y se marca stale.
    policy = VerificationPolicy(ResearchConfig(staleness_days=30))
    claim = Claim(field="importe", value="50000", is_critical=True, sources=[hint.source_ref])
    assert policy.needs_revalidation(claim, intent="explore", now=datetime.now(UTC)) is True
    assert claim.stale is True
