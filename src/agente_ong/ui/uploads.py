"""Documentos del proyecto: subida segura bajo `RECURSOS/[nombre_proyecto]/` (R3).

Política (confirmada en design.md):
  - Whitelist de extensiones: PDF, DOCX, TXT, JPG, PNG.
  - Tamaño máximo: 10 MB por archivo.
  - Sin path traversal: el nombre de proyecto y el de archivo se validan y la ruta final se
    normaliza (`resolve()`) verificando que queda DENTRO de la carpeta esperada.
  - Colisión de nombre: renombrado automático `nombre (2).ext`, `nombre (3).ext`, …

Los errores de validación se lanzan como `UploadError` con mensaje claro para el usuario.
`RECURSOS/ENTRENAMIENTO/` es del investigador; los proyectos no pueden llamarse así.
"""

from __future__ import annotations

from pathlib import Path

# Whitelist de extensiones permitidas (en minúsculas, sin punto).
ALLOWED_EXT = {"pdf", "docx", "txt", "jpg", "png"}

# Tamaño máximo por archivo: 10 MB.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Raíz de los documentos de proyectos (relativa a la raíz de la app, como en structure.md).
RECURSOS_ROOT = Path("RECURSOS")

# Carpeta reservada del investigador dentro de RECURSOS/ (no es un proyecto).
_RESERVED_DIRS = {"entrenamiento"}

# Caracteres prohibidos en nombres (separadores y reservados de Windows).
_FORBIDDEN_CHARS = set('<>:"/\\|?*')


class UploadError(ValueError):
    """Subida rechazada: nombre, tipo o tamaño no válidos (mensaje apto para el usuario)."""


def project_dir(name: str, *, root: Path = RECURSOS_ROOT) -> Path:
    """Ruta de la carpeta de documentos de un proyecto, validada contra path traversal.

    Normaliza con `resolve()` y verifica que el resultado queda dentro de `root`; un nombre
    con separadores, `..`, caracteres prohibidos o reservado lanza `UploadError`. NO crea la
    carpeta (eso lo hace quien escribe).
    """
    _validate_component(name, what="nombre de proyecto")
    if name.strip().lower() in _RESERVED_DIRS:
        raise UploadError(f"'{name}' es una carpeta reservada del sistema.")
    base = root.resolve()
    target = (base / name.strip()).resolve()
    if target.parent != base:
        raise UploadError(f"Nombre de proyecto no válido: {name!r}.")
    return target


def validate_filename(filename: str) -> None:
    """Valida el nombre de archivo: sin rutas ni traversal, extensión en la whitelist."""
    _validate_component(filename, what="nombre de archivo")
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXT:
        allowed = ", ".join(sorted(e.upper() for e in ALLOWED_EXT))
        raise UploadError(
            f"Tipo de archivo no permitido: '.{ext or '?'}'. Tipos admitidos: {allowed}."
        )


def validate_size(data: bytes) -> None:
    """Valida el tamaño del contenido contra `MAX_UPLOAD_BYTES` (R3.3)."""
    if len(data) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise UploadError(f"El archivo supera el tamaño máximo de {mb} MB.")


def save_upload(name: str, filename: str, data: bytes, *, root: Path = RECURSOS_ROOT) -> Path:
    """Guarda un documento del proyecto y devuelve su ruta final (R3.1).

    Valida proyecto, nombre y tamaño; crea la carpeta si no existe; ante colisión de nombre
    renombra automáticamente a `nombre (2).ext`, `nombre (3).ext`, … sin sobrescribir (R3.5).
    """
    validate_filename(filename)
    validate_size(data)
    directory = project_dir(name, root=root)
    directory.mkdir(parents=True, exist_ok=True)
    target = _next_free_path(directory / filename.strip())
    target.write_bytes(data)
    return target


def list_documents(name: str, *, root: Path = RECURSOS_ROOT) -> list[Path]:
    """Documentos del proyecto, orden alfabético; carpeta inexistente => lista vacía (R3.4)."""
    directory = project_dir(name, root=root)
    if not directory.is_dir():
        return []
    return sorted((p for p in directory.iterdir() if p.is_file()), key=lambda p: p.name.lower())


def delete_document(name: str, filename: str, *, root: Path = RECURSOS_ROOT) -> None:
    """Borra un documento del proyecto; el nombre se valida igual que al guardar.

    Solo borra archivos directamente bajo la carpeta del proyecto; si no existe, lanza
    `UploadError` (mensaje claro en lugar de un FileNotFoundError críptico).
    """
    _validate_component(filename, what="nombre de archivo")
    directory = project_dir(name, root=root)
    target = (directory / filename.strip()).resolve()
    if target.parent != directory or not target.is_file():
        raise UploadError(f"El documento {filename!r} no existe en el proyecto {name!r}.")
    target.unlink()


def _next_free_path(path: Path) -> Path:
    """Primera ruta libre: `path` tal cual o `nombre (N).ext` con N creciente desde 2."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _validate_component(value: str, *, what: str) -> None:
    """Un único componente de ruta: no vacío, sin separadores, sin `..`, sin reservados."""
    clean = (value or "").strip()
    if not clean:
        raise UploadError(f"El {what} no puede estar vacío.")
    if Path(clean).is_absolute() or clean != Path(clean).name or clean in (".", ".."):
        raise UploadError(f"{what.capitalize()} no válido: {value!r}.")
    if any(ch in _FORBIDDEN_CHARS or ord(ch) < 32 for ch in clean):
        raise UploadError(f"{what.capitalize()} con caracteres no permitidos: {value!r}.")
