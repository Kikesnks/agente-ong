"""Presentación de resultados: orden por fiabilidad y filtros (R11).

Funciones PURAS, sin dependencia de Streamlit, para que la lógica sea testeable: el orden
canónico va de más a menos fiable (VERIFIED → OFFICIAL_UNCROSSED → UNCROSSED_UNVERIFIED →
CONFLICTING → NOT_FOUND) y los filtros tratan explícitamente los datos no encontrados
(`Claim.value is None`): cuando un filtro por año o importe está activo, una convocatoria
sin ese dato queda EXCLUIDA — nunca se interpreta como cero ni como año remoto (R11.3).

La capa Streamlit (`render_report`, tarea 27) se añade encima de estas funciones.
"""

from __future__ import annotations

import re

from agente_ong.research.models import GrantOpportunity, VerificationStatus

# Orden canónico de presentación: de más a menos fiable (R11.1).
STATUS_ORDER: tuple[VerificationStatus, ...] = (
    VerificationStatus.VERIFIED,
    VerificationStatus.OFFICIAL_UNCROSSED,
    VerificationStatus.UNCROSSED_UNVERIFIED,
    VerificationStatus.CONFLICTING,
    VerificationStatus.NOT_FOUND,
)
_STATUS_RANK = {status: rank for rank, status in enumerate(STATUS_ORDER)}

# Años plausibles de una convocatoria (evita confundir importes con años).
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def sort_opportunities(opportunities: list[GrantOpportunity]) -> list[GrantOpportunity]:
    """Ordena por estado de verificación (orden canónico), de forma estable.

    La estabilidad preserva el orden de llegada dentro de cada estado (no se inventa un
    segundo criterio).
    """
    return sorted(opportunities, key=lambda opp: _STATUS_RANK[opp.overall_status])


def filter_opportunities(
    opportunities: list[GrantOpportunity],
    *,
    status: VerificationStatus | None = None,
    min_year: int | None = None,
    min_amount: float | None = None,
) -> list[GrantOpportunity]:
    """Filtra por estado, año del plazo y/o importe mínimo; los criterios se combinan (AND).

    Con `min_year`/`min_amount` activos, las convocatorias cuyo dato es `None` (o no
    parseable) se excluyen del resultado (R11.3: nunca tratarlas como valor cero). No
    reordena: aplicar sobre una lista ya ordenada mantiene el orden (R11.4).
    """
    result = opportunities
    if status is not None:
        result = [o for o in result if o.overall_status == status]
    if min_year is not None:
        result = [
            o
            for o in result
            if (year := _claim_year(o.deadline.value)) is not None and year >= min_year
        ]
    if min_amount is not None:
        result = [
            o
            for o in result
            if (amount := _claim_amount(o.amount.value)) is not None and amount >= min_amount
        ]
    return result


def _claim_year(value: str | None) -> int | None:
    """Año contenido en el valor de un claim de plazo; None si falta o no es parseable."""
    if value is None:
        return None
    match = _YEAR_RE.search(value)
    return int(match.group(0)) if match else None


def _claim_amount(value: str | None) -> float | None:
    """Importe numérico del valor de un claim; None si falta o no es parseable.

    Acepta formatos habituales de las fuentes: "120000", "120.000 €", "120.000,50 EUR",
    "120,000.50". No adivina: si no hay un número reconocible, devuelve None.
    """
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.,]", "", value)
    if not re.search(r"\d", cleaned):
        return None
    # Si hay ambos separadores, el ÚLTIMO es el decimal; el otro agrupa miles.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Solo coma: decimal si parece "123,45"; agrupación si parece "120,000".
        head, _, tail = cleaned.rpartition(",")
        cleaned = f"{head.replace(',', '')}.{tail}" if len(tail) != 3 else cleaned.replace(",", "")
    elif cleaned.count(".") > 1 or (
        "." in cleaned and len(cleaned.rpartition(".")[2]) == 3 and len(cleaned) > 4
    ):
        # Varios puntos, o un único punto con grupo de 3 (formato es-ES "120.000"): miles.
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None
