"""Limpieza heurística del texto extraído de páginas web (R18 de investigador-v2).

El contenido leído de webs llega con elementos de plantilla (menús de navegación, avisos de
cookies, selectores de idioma, footers, formularios de suscripción) que en la prueba de
producción del 12-06-2026 acabaron en los campos del informe ("Skip to content", "ES / CAT",
"Nuestra web utiliza cookies…"). `clean_text` filtra esas líneas y normaliza el espaciado;
`snippet` acota un texto a una longitud máxima cortando en límite de palabra.

Heurístico y deliberadamente conservador: el objetivo es una mejora drástica, no la
perfección, y NUNCA descartar contenido útil (ante la duda, se conserva la línea).
"""

from __future__ import annotations

import re

# Subcadenas (en minúsculas) que delatan una línea de plantilla web. Si una línea las
# contiene Y es razonablemente corta, se descarta (el límite de longitud evita tirar un
# párrafo legítimo que mencione "cookie" de pasada).
_TEMPLATE_MARKERS = (
    "skip to content",
    "saltar al contenido",
    "ir al contenido",
    "utiliza cookies",
    "usamos cookies",
    "uso de cookies",
    "política de cookies",
    "política de privacidad",
    "aviso legal",
    "acepto",
    "aceptar cookies",
    "newsletter",
    "suscríbete",
    "suscribete",
    "boletín",
    "síguenos",
    "siguenos",
    "compartir en",
    "menú principal",
    "menu principal",
    "volver arriba",
    "todos los derechos reservados",
)

# Líneas que son solo un selector de idioma ("ES / CAT / EN", "ES | EN"). Códigos de 2-3
# letras (es, cat, eng…) separados por / | ·.
_LANG_SELECTOR_RE = re.compile(
    r"^\s*(?:[a-z]{2,3}\s*[/|·]\s*){1,}[a-z]{2,3}\s*$", re.IGNORECASE
)

# Longitud máxima de una línea para considerarla "de plantilla" si trae un marcador.
_TEMPLATE_LINE_MAX = 120


def clean_text(text: str | None) -> str:
    """Filtra elementos de plantilla web y normaliza el espaciado del texto.

    - Descarta líneas con marcadores de cookies/navegación/suscripción/redes (si son
      cortas), selectores de idioma y líneas vacías redundantes.
    - Colapsa espacios múltiples y líneas duplicadas consecutivas.
    Devuelve "" si la entrada es None o queda vacía tras limpiar.
    """
    if not text:
        return ""

    kept: list[str] = []
    prev: str | None = None
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            continue
        if _is_template_line(line):
            continue
        if line == prev:  # línea duplicada consecutiva (típico de menús repetidos)
            continue
        kept.append(line)
        prev = line
    return "\n".join(kept)


def _is_template_line(line: str) -> bool:
    lowered = line.lower()
    if _LANG_SELECTOR_RE.match(line):
        return True
    if len(line) <= _TEMPLATE_LINE_MAX and any(m in lowered for m in _TEMPLATE_MARKERS):
        return True
    return False


def snippet(text: str | None, max_chars: int) -> str:
    """Acota `text` a `max_chars`, cortando en el último espacio y añadiendo elipsis.

    No parte palabras por la mitad; si no hay espacio donde cortar, trunca en seco. Una
    entrada ya corta se devuelve tal cual.
    """
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    cut = collapsed[:max_chars].rstrip()
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space].rstrip()
    return cut + "…"
