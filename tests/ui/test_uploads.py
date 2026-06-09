"""Tests de la subida de documentos (`ui/uploads.py`).

Seguridad (path traversal, whitelist de tipos, límite de 10 MB), renombrado automático ante
colisión y escritura dentro de `RECURSOS/[proyecto]/`. _Requirements: 3.1, 3.2, 3.3, 3.5_
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agente_ong.ui.uploads import (
    ALLOWED_EXT,
    MAX_UPLOAD_BYTES,
    UploadError,
    delete_document,
    list_documents,
    project_dir,
    save_upload,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Raíz RECURSOS/ aislada del test (no toca la carpeta real del repo)."""
    recursos = tmp_path / "RECURSOS"
    recursos.mkdir()
    return recursos


# --- project_dir: sin path traversal (R3.2) ---


def test_project_dir_stays_inside_recursos(root: Path) -> None:
    target = project_dir("Mi ONG", root=root)
    assert target.parent == root.resolve()
    assert target.name == "Mi ONG"


@pytest.mark.parametrize(
    "bad_name",
    ["../fuera", "..", "a/b", "a\\b", "con|barra", "fin:", "   ", "ENTRENAMIENTO"],
)
def test_project_dir_rejects_traversal_and_reserved(root: Path, bad_name: str) -> None:
    with pytest.raises(UploadError):
        project_dir(bad_name, root=root)


def test_project_dir_rejects_absolute_path(root: Path, tmp_path: Path) -> None:
    with pytest.raises(UploadError):
        project_dir(str(tmp_path / "fuera"), root=root)


# --- Validación de tipo y tamaño (R3.2/R3.3) ---


@pytest.mark.parametrize("filename", ["doc.pdf", "doc.DOCX", "notas.txt", "foto.JPG", "img.png"])
def test_whitelisted_extensions_are_accepted(root: Path, filename: str) -> None:
    saved = save_upload("ONG", filename, b"contenido", root=root)
    assert saved.is_file()


@pytest.mark.parametrize("filename", ["script.exe", "macro.docm", "pagina.html", "sin_extension"])
def test_non_whitelisted_extensions_are_rejected(root: Path, filename: str) -> None:
    with pytest.raises(UploadError):
        save_upload("ONG", filename, b"contenido", root=root)
    assert not (root / "ONG").exists(), "un rechazo no debe dejar nada escrito"


@pytest.mark.parametrize("filename", ["../evil.pdf", "..\\evil.pdf", "a/b.pdf", "C:\\x\\e.pdf"])
def test_traversal_filenames_are_rejected(root: Path, filename: str) -> None:
    with pytest.raises(UploadError):
        save_upload("ONG", filename, b"contenido", root=root)


def test_oversized_file_is_rejected(root: Path) -> None:
    with pytest.raises(UploadError):
        save_upload("ONG", "grande.pdf", b"x" * (MAX_UPLOAD_BYTES + 1), root=root)


def test_file_at_limit_is_accepted(root: Path) -> None:
    saved = save_upload("ONG", "justo.pdf", b"x" * MAX_UPLOAD_BYTES, root=root)
    assert saved.stat().st_size == MAX_UPLOAD_BYTES


def test_allowed_ext_is_the_agreed_whitelist() -> None:
    assert ALLOWED_EXT == {"pdf", "docx", "txt", "jpg", "png"}


# --- Escritura, colisiones y gestión (R3.1/R3.5) ---


def test_save_writes_inside_project_folder(root: Path) -> None:
    saved = save_upload("Mi ONG", "memoria.pdf", b"datos", root=root)
    assert saved == root.resolve() / "Mi ONG" / "memoria.pdf"
    assert saved.read_bytes() == b"datos"


def test_collision_renames_automatically_without_overwriting(root: Path) -> None:
    first = save_upload("ONG", "memoria.pdf", b"v1", root=root)
    second = save_upload("ONG", "memoria.pdf", b"v2", root=root)
    third = save_upload("ONG", "memoria.pdf", b"v3", root=root)

    assert (first.name, second.name, third.name) == (
        "memoria.pdf",
        "memoria (2).pdf",
        "memoria (3).pdf",
    )
    assert first.read_bytes() == b"v1", "el original no se sobrescribe"


def test_list_documents_sorted_and_empty_for_missing_project(root: Path) -> None:
    save_upload("ONG", "b.txt", b"2", root=root)
    save_upload("ONG", "A.pdf", b"1", root=root)
    assert [p.name for p in list_documents("ONG", root=root)] == ["A.pdf", "b.txt"]
    assert list_documents("Inexistente", root=root) == []


def test_delete_document_removes_file_and_rejects_missing(root: Path) -> None:
    save_upload("ONG", "tmp.txt", b"x", root=root)
    delete_document("ONG", "tmp.txt", root=root)
    assert list_documents("ONG", root=root) == []
    with pytest.raises(UploadError):
        delete_document("ONG", "tmp.txt", root=root)
