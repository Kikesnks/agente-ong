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


def _validate_component(value: str, *, what: str) -> None:
    """Un único componente de ruta: no vacío, sin separadores, sin `..`, sin reservados."""
    clean = (value or "").strip()
    if not clean:
        raise UploadError(f"El {what} no puede estar vacío.")
    if Path(clean).is_absolute() or clean != Path(clean).name or clean in (".", ".."):
        raise UploadError(f"{what.capitalize()} no válido: {value!r}.")
    if any(ch in _FORBIDDEN_CHARS or ord(ch) < 32 for ch in clean):
        raise UploadError(f"{what.capitalize()} con caracteres no permitidos: {value!r}.")
