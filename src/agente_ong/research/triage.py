"""Pre-clasificación heurística de resultados (`result_type`, R20 de investigador-v2).

Asigna a cada `SearchHit` un `ResultType` provisional para que el usuario distinga de un
vistazo lo accionable (una convocatoria) del material de contexto (estudios, noticias), y
para dejar el terreno preparado al filtrado semántico con LLM de la SPEC 2+ (que NO se
implementa aquí). Es una heurística simple y deliberadamente prudente; no decide nada
irreversible (el dato es retrocompatible y opcional).
"""

from __future__ import annotations

import re

from agente_ong.research.models import ResultType, SearchHit

# Señales léxicas de OFERTA de financiación (no de ejecución). En minúsculas.
_STRONG_SIGNALS = (
    "convocatoria",
    "bases reguladoras",
    "plazo de presentación",
    "plazo de solicitud",
    "presentación de solicitudes",
    "dotación",
    "subvencion",  # tolerante a falta de tilde en textos scrapeados
    "subvención",
)

# Importe explícito: símbolo de euro o "euros" junto a una cifra.
_AMOUNT_RE = re.compile(r"(€|\beuros?\b)", re.IGNORECASE)
_DIGIT_RE = re.compile(r"\d")

# Dominios oficiales donde una página suele ser la convocatoria en sí.
_OFFICIAL_DOMAINS = (".gob.es", ".gov", "europa.eu", "sede.", "boe.es", ".gencat.cat")


def classify_hit(hit: SearchHit) -> ResultType:
    """Clasifica un hit en `convocatoria_probable` / `documento_informativo` / `desconocido`.

    Reglas (design R20):
      - BDNS (fuente cuyo corpus es solo convocatorias) -> convocatoria_probable.
      - >= 2 señales fuertes en título+snippet, o dominio oficial -> convocatoria_probable.
      - Tavily (no oficial) sin señal fuerte -> documento_informativo (tope de R16.5).
      - Resto -> desconocido.
    """
    if hit.source_name == "bdns":
        return "convocatoria_probable"

    text = f"{hit.title or ''} {hit.snippet or ''}".lower()
    signals = sum(1 for s in _STRONG_SIGNALS if s in text)
    has_amount = bool(_AMOUNT_RE.search(text) and _DIGIT_RE.search(text))
    strong = signals + (1 if has_amount else 0)

    if strong >= 2 or _is_official_domain(hit.url):
        return "convocatoria_probable"
    if hit.source_name == "tavily":
        return "documento_informativo"
    return "desconocido"


def _is_official_domain(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return any(token in lowered for token in _OFFICIAL_DOMAINS)


# Prioridad para elegir el "mejor" tipo de un grupo de hits (misma convocatoria).
_RANK = {"convocatoria_probable": 2, "desconocido": 1, "documento_informativo": 0}


def best_result_type(types: list[ResultType]) -> ResultType:
    """Devuelve el tipo más informativo de un grupo (convocatoria > desconocido > informativo)."""
    if not types:
        return "desconocido"
    return max(types, key=lambda t: _RANK[t])
