"""Test de integración del modo training (captura de material de entrenamiento, end-to-end).

Ejecuta `Investigador.run` en modo "training" con FS temporal y persistencia SQLite real:
verifica que los documentos se capturan bajo `RECURSOS/ENTRENAMIENTO/`, con su sidecar de
metadatos e índice en el store, y que NO se re-descargan en una segunda investigación.
_Requirements: 2.2, 2.4, 2.5_
"""

import json
from pathlib import Path

import pytest

from agente_ong.research.config import ResearchConfig
from agente_ong.research.investigador import Investigador
from agente_ong.research.models import ResearchRequest
from agente_ong.research.store.sqlite import SqliteStore
from agente_ong.research.urlnorm import normalize_url
from fakes import FakeFetchSource, FakeSearchSource, make_document, make_hit

P1 = "https://ejemplos.es/proyectos/aprobado.pdf"


@pytest.fixture
def config(tmp_path: Path) -> ResearchConfig:
    return ResearchConfig(
        max_depth=1,
        db_path=tmp_path / "agente_ong.db",
        entrenamiento_path=tmp_path / "RECURSOS" / "ENTRENAMIENTO",
    )


def _sources():
    search = FakeSearchSource(
        name="tavily", hits=[make_hit(P1, source_name="tavily", title="Proyecto aprobado")]
    )
    fetch = FakeFetchSource(
        documents={
            P1: make_document(
                P1, text="", raw_bytes=b"%PDF-1.4 proyecto", content_type="application/pdf"
            )
        }
    )
    return search, fetch


def _training_request() -> ResearchRequest:
    return ResearchRequest(mode="training", query_terms=["cultura"])


# --- Captura bajo RECURSOS/ENTRENAMIENTO con sidecar e índice (Req 2.2, 2.4) ---


def test_training_captures_file_with_sidecar_and_index(config: ResearchConfig) -> None:
    search, fetch = _sources()
    with Investigador(config, sources=[search, fetch]) as inv:
        report = inv.run(_training_request())

    assert report.mode == "training"
    assert len(report.resources) == 1
    resource = report.resources[0]

    path = Path(resource.path)
    assert path.exists()
    assert path.is_relative_to(config.entrenamiento_path)  # bajo RECURSOS/ENTRENAMIENTO/
    assert path.suffix == ".pdf"
    assert path.read_bytes() == b"%PDF-1.4 proyecto"
    assert resource.mode_of_capture == "download"
    assert resource.tags == ["cultura"]  # tags = términos de la investigación

    # Sidecar de metadatos (Req 2.4).
    sidecar = Path(resource.path + ".meta.json")
    assert sidecar.exists()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["source_url"] == P1
    assert meta["tags"] == ["cultura"]

    # Índice de capturas en el store persistente.
    store = SqliteStore(config.db_path)
    assert store.has_url(P1) is True
    assert len(store.list_resources()) == 1
    store.close()


# --- No se re-descarga en una segunda investigación (Req 2.5) ---


def test_training_does_not_redownload_known_resource(config: ResearchConfig) -> None:
    search1, fetch1 = _sources()
    with Investigador(config, sources=[search1, fetch1]) as inv1:
        report1 = inv1.run(_training_request())
    captured = Path(report1.resources[0].path)

    # Marcamos el archivo capturado con un centinela: si NO se re-descarga, se conserva.
    captured.write_bytes(b"CENTINELA")

    # Segunda investigación: instancia nueva, mismo .db y misma carpeta de entrenamiento.
    search2, fetch2 = _sources()
    with Investigador(config, sources=[search2, fetch2]) as inv2:
        report2 = inv2.run(_training_request())

    # El recurso ya estaba en el índice -> no se re-descarga ni se sobrescribe.
    assert captured.read_bytes() == b"CENTINELA"
    assert report2.resources[0].path == report1.resources[0].path

    # El índice no duplica el recurso.
    store = SqliteStore(config.db_path)
    assert len(store.list_resources()) == 1
    assert store.has_url(normalize_url(P1)) is True
    store.close()
