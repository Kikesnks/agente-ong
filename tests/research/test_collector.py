"""Tests de `TrainingCollector` (captura de material de entrenamiento).

Usa un FS temporal: descarga binaria vs copia de texto, sidecar de metadatos, rechazo de
path traversal y no re-descarga de URL ya capturada. _Requirements: 2.2, 2.5, NFR Security_
"""

import json
from pathlib import Path

import pytest

from agente_ong.research.collector import TrainingCollector
from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import FetchedDocument
from agente_ong.research.store.memory import InMemoryStore


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    return tmp_path / "ENTRENAMIENTO"


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def collector(base_dir: Path, store: InMemoryStore) -> TrainingCollector:
    return TrainingCollector(ResearchConfig(entrenamiento_path=base_dir), store=store)


def _binary_doc() -> FetchedDocument:
    return FetchedDocument(
        url="https://x.es/docs/proyecto.pdf",
        content_text="",
        raw_bytes=b"%PDF-1.4 datos",
        content_type="application/pdf",
        title="Proyecto X",
    )


def _text_doc() -> FetchedDocument:
    return FetchedDocument(
        url="https://y.es/articulo",
        content_text="# Texto\ncontenido",
        raw_bytes=None,
        content_type="text/html",
    )


# --- Descarga binaria vs copia de texto (Requirement 2.2/2.3) ---


def test_collect_binary_download(collector: TrainingCollector, base_dir: Path) -> None:
    resource = collector.collect(_binary_doc(), tags=["cultura", "aprobado"])
    path = Path(resource.path)

    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.read_bytes() == b"%PDF-1.4 datos"
    assert resource.mode_of_capture == "download"
    assert resource.tags == ["cultura", "aprobado"]
    assert path.is_relative_to(base_dir)


def test_collect_text_copy(collector: TrainingCollector) -> None:
    resource = collector.collect(_text_doc())
    path = Path(resource.path)

    assert path.suffix == ".md"
    assert path.read_text(encoding="utf-8").startswith("# Texto")
    assert resource.mode_of_capture == "text_copy"


# --- Sidecar de metadatos (Requirement 2.4) ---


def test_collect_writes_metadata_sidecar(collector: TrainingCollector) -> None:
    resource = collector.collect(_binary_doc(), tags=["aprobado"])
    sidecar = Path(resource.path + ".meta.json")

    assert sidecar.exists()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["source_url"] == "https://x.es/docs/proyecto.pdf"
    assert meta["title"] == "Proyecto X"
    assert meta["tags"] == ["aprobado"]
    assert meta["mode_of_capture"] == "download"
    assert "captured_at" in meta


# --- Deduplicación (Requirement 2.5) ---


def test_does_not_redownload_known_url(
    collector: TrainingCollector, store: InMemoryStore
) -> None:
    first = collector.collect(_binary_doc())
    before = len(store.list_resources())

    # Misma URL en forma equivalente (mayúsculas + fragmento) -> no re-descarga.
    second = collector.collect(
        FetchedDocument(url="HTTPS://X.es/docs/proyecto.pdf#frag", content_text="", raw_bytes=b"OTRO")
    )

    assert len(store.list_resources()) == before  # no añade un nuevo recurso
    assert second.path == first.path
    assert Path(first.path).read_bytes() == b"%PDF-1.4 datos"  # no se sobrescribió


def test_index_tracks_each_distinct_url(
    collector: TrainingCollector, store: InMemoryStore
) -> None:
    collector.collect(_binary_doc())
    collector.collect(_text_doc())
    assert len(store.list_resources()) == 2
    assert store.has_url("https://x.es/docs/proyecto.pdf")
    assert store.has_url("https://y.es/articulo")


# --- Anti path-traversal (NFR Security) ---


def test_resolve_within_base_rejects_escape(
    collector: TrainingCollector, base_dir: Path
) -> None:
    with pytest.raises(ValueError):
        collector._resolve_within_base(base_dir / ".." / ".." / "evil.txt")


def test_traversal_like_url_stays_within_base(
    collector: TrainingCollector, base_dir: Path
) -> None:
    # Una URL con "../" en la ruta no debe escapar del directorio base.
    doc = FetchedDocument(
        url="https://evil.com/a/../../etc/passwd", content_text="x", raw_bytes=None
    )
    resource = collector.collect(doc)
    path = Path(resource.path)
    assert path.parent == base_dir
    assert path.is_relative_to(base_dir)


# --- Portabilidad: funciona sin store (Requirement 7.1) ---


def test_works_without_store(base_dir: Path) -> None:
    collector = TrainingCollector(ResearchConfig(entrenamiento_path=base_dir), store=None)
    resource = collector.collect(_text_doc())
    assert Path(resource.path).exists()
    # Sin store no hay deduplicación: vuelve a escribir sin fallar.
    again = collector.collect(_text_doc())
    assert again.path == resource.path
