"""Nombrado de los informes descargables (decisión #25).

`slugify_project_name` sanea el nombre de un proyecto a un slug apto para nombre de
archivo (sin tildes, espacios ni símbolos); `build_report_filename` compone el nombre final
`informe_[slug]_[fecha].md` / `informe_detallado_[slug]_[fecha].md`. Ambas funciones son
puras: no dependen de `Project` ni de `ResearchRun`, para poder testearlas sin Streamlit ni
la capa de persistencia.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Literal

MAX_SLUG_LENGTH = 60

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify_project_name(name: str, *, fallback: str) -> str:
    """Sanea `name` a un slug apto para nombre de archivo; usa `fallback` si queda vacío.

    Quita tildes/eñes (NFKD + ascii), pasa a minúsculas, sustituye todo lo que no sea
    `[a-z0-9]` por `_` (colapsando repeticiones) y recorta a `MAX_SLUG_LENGTH`. Si el
    resultado queda vacío (p.ej. `name` solo tenía símbolos o alfabeto no latino), se aplica
    el mismo saneo a `fallback`; si incluso así queda vacío, se devuelve `"proyecto"`.
    """
    slug = _slugify(name)
    if slug:
        return slug
    slug = _slugify(fallback)
    return slug or "proyecto"


def _slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("_", ascii_value.lower()).strip("_")
    return slug[:MAX_SLUG_LENGTH].rstrip("_")


def build_report_filename(
    *, project_slug: str, created_at: date, kind: Literal["summary", "detailed"]
) -> str:
    """Nombre del informe descargable: `informe_[detallado_]{slug}_{YYYY-MM-DD}.md`."""
    fecha = created_at.isoformat()
    if kind == "detailed":
        return f"informe_detallado_{project_slug}_{fecha}.md"
    return f"informe_{project_slug}_{fecha}.md"
