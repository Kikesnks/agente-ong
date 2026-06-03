"""Captura de proyectos aprobados como material de entrenamiento (`TrainingCollector`).

Guarda en local, bajo `RECURSOS/ENTRENAMIENTO/`, los documentos que el agente investigador
encuentra como referencia (proyectos aprobados, plantillas). Si el documento es descargable
(trae `raw_bytes`) guarda el binario; si no, guarda el texto extraído. Junto a cada recurso
escribe un sidecar `.meta.json` con sus metadatos (URL de origen, fecha, etiquetas...).

Seguridad: el nombre de archivo se deriva de la URL pero se sanitiza (sin separadores ni
`..`) y, como defensa en profundidad, se valida que la ruta resultante quede DENTRO del
directorio base (anti path-traversal, NFR Security). Si la URL ya fue capturada
(`ResearchStore.has_url`), no se vuelve a descargar (Requirement 2.5).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import FetchedDocument, StoredResource
from agente_ong.research.store.base import ResearchStore
from agente_ong.research.urlnorm import normalize_url

# Mapa mínimo de content-type -> extensión para descargas binarias.
_CONTENT_TYPE_EXT = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


class TrainingCollector:
    """Descarga o copia en local los recursos de entrenamiento, con índice y deduplicación."""

    def __init__(self, config: ResearchConfig, store: ResearchStore | None = None) -> None:
        self._config = config
        self._store = store
        self._base = Path(config.entrenamiento_path)

    def collect(self, doc: FetchedDocument, tags: list[str] | None = None) -> StoredResource:
        """Captura `doc` bajo RECURSOS/ENTRENAMIENTO/ y devuelve el `StoredResource`.

        Si la URL ya estaba en el índice, no re-descarga y devuelve el recurso existente.
        """
        tags = list(tags or [])

        # Deduplicación: si ya se capturó esta URL, no re-descargar (Requirement 2.5).
        if self._store is not None and self._store.has_url(doc.url):
            existing = self._find_existing(doc.url)
            if existing is not None:
                return existing

        self._base.mkdir(parents=True, exist_ok=True)

        is_binary = doc.raw_bytes is not None
        file_path = self._base / self._safe_filename(doc, is_binary)
        full = self._resolve_within_base(file_path)

        if is_binary:
            full.write_bytes(doc.raw_bytes or b"")
            mode = "download"
        else:
            full.write_text(doc.content_text or "", encoding="utf-8")
            mode = "text_copy"

        resource = StoredResource(
            path=str(file_path),
            source_url=doc.url,
            mode_of_capture=mode,
            captured_at=datetime.now(timezone.utc),
            tags=tags,
        )
        self._write_sidecar(full, doc, resource)

        if self._store is not None:
            self._store.add_resource(resource)
        return resource

    # --- Internos ---

    def _find_existing(self, url: str) -> StoredResource | None:
        if self._store is None:
            return None
        target = normalize_url(url)
        for resource in self._store.list_resources():
            if normalize_url(resource.source_url) == target:
                return resource
        return None

    def _safe_filename(self, doc: FetchedDocument, is_binary: bool) -> str:
        """Nombre de archivo seguro derivado de la URL (sin separadores ni `..`)."""
        path = urlsplit(doc.url).path
        last_segment = path.rsplit("/", 1)[-1]
        if "." in last_segment:
            stem, url_ext = last_segment.rsplit(".", 1)
        else:
            stem, url_ext = last_segment, ""

        safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem).strip("_")
        if not safe_stem:
            netloc = urlsplit(doc.url).netloc
            safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", netloc).strip("_") or "recurso"

        # Hash de la URL normalizada para garantizar unicidad sin colisiones.
        digest = hashlib.sha256(normalize_url(doc.url).encode("utf-8")).hexdigest()[:10]
        extension = self._extension(doc, is_binary, url_ext)
        return f"{safe_stem}-{digest}{extension}"

    @staticmethod
    def _extension(doc: FetchedDocument, is_binary: bool, url_ext: str) -> str:
        if not is_binary:
            # El texto extraído (markdown de Firecrawl u otro) se guarda como .md.
            return ".md"
        safe_ext = re.sub(r"[^A-Za-z0-9]", "", url_ext).lower()
        if safe_ext:
            return f".{safe_ext}"
        content_type = (doc.content_type or "").split(";")[0].strip().lower()
        return _CONTENT_TYPE_EXT.get(content_type, ".bin")

    def _resolve_within_base(self, path: Path) -> Path:
        """Valida que `path` quede dentro del directorio base; si no, rechaza (anti traversal)."""
        base = self._base.resolve()
        full = path.resolve()
        if not full.is_relative_to(base):
            raise ValueError(
                f"Ruta fuera del directorio de entrenamiento (posible path traversal): {path}"
            )
        return full

    def _write_sidecar(
        self, full: Path, doc: FetchedDocument, resource: StoredResource
    ) -> None:
        meta = {
            "source_url": resource.source_url,
            "captured_at": resource.captured_at.isoformat(),
            "tags": resource.tags,
            "mode_of_capture": resource.mode_of_capture,
            "title": doc.title,
            "content_type": doc.content_type,
        }
        sidecar = full.with_name(full.name + ".meta.json")
        sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
