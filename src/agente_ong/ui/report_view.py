"""Presentación de resultados: orden por fiabilidad, filtros y render (R4/R7/R11).

Dos capas en este módulo:
  - Funciones PURAS, sin dependencia de Streamlit, para que la lógica sea testeable: el
    orden canónico va de más a menos fiable (VERIFIED → OFFICIAL_UNCROSSED →
    UNCROSSED_UNVERIFIED → CONFLICTING → NOT_FOUND) y los filtros tratan explícitamente los
    datos no encontrados (`Claim.value is None`): con un filtro por año o importe activo,
    una convocatoria sin ese dato queda EXCLUIDA — nunca es cero ni año remoto (R11.3).
  - `render_report`: capa Streamlit FINA encima de las puras (badges de estado, lista
    ordenada/filtrable, `unresolved`, `failed_sources` y descarga en Markdown). Streamlit
    se importa perezosamente solo ahí.
"""

from __future__ import annotations

import re

from agente_ong.research.models import GrantOpportunity, ResearchReport, VerificationStatus
from agente_ong.ui.report_serde import report_to_markdown

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


# --- Capa Streamlit (fina; toda la lógica vive en las funciones puras de arriba) ---

# Badge y etiqueta legible por estado, en el orden canónico.
_STATUS_BADGES = {
    VerificationStatus.VERIFIED: "🟢 Verificado (2+ fuentes)",
    VerificationStatus.OFFICIAL_UNCROSSED: "🔵 Fuente oficial (sin cruzar)",
    VerificationStatus.UNCROSSED_UNVERIFIED: "🟡 Sin verificar (1 fuente no oficial)",
    VerificationStatus.CONFLICTING: "🟠 Fuentes contradictorias",
    VerificationStatus.NOT_FOUND: "🔴 No encontrado",
}

# Datos de la convocatoria a mostrar: (atributo, etiqueta).
_CLAIM_ROWS = [
    ("organism", "Organismo"),
    ("amount", "Importe"),
    ("deadline", "Plazo"),
    ("scope", "Ámbito"),
    ("url", "URL"),
]


def status_badge(status: VerificationStatus) -> str:
    """Badge legible de un estado de verificación (R4.2)."""
    return _STATUS_BADGES[status]


def render_report(report: ResearchReport, *, key: str = "report") -> None:
    """Renderiza un informe: lista ordenada y filtrable, incidencias y descarga (R4/R7/R11).

    `key` aísla los widgets cuando se renderizan varios informes en la misma página.
    """
    import streamlit as st  # import perezoso: las funciones puras no requieren Streamlit

    opportunities = sort_opportunities(report.opportunities)

    if opportunities:
        st.caption(f"{len(opportunities)} convocatoria(s), ordenadas de más a menos fiable.")
        with st.expander("Filtros"):
            status_options: list[VerificationStatus | None] = [None, *STATUS_ORDER]
            chosen_status = st.selectbox(
                "Estado de verificación",
                status_options,
                format_func=lambda s: "Todos" if s is None else status_badge(s),
                key=f"{key}-filter-status",
            )
            year_text = st.text_input(
                "Año mínimo del plazo (vacío = sin filtro)", key=f"{key}-filter-year"
            )
            amount_text = st.text_input(
                "Importe mínimo en € (vacío = sin filtro)", key=f"{key}-filter-amount"
            )
        min_year = int(year_text) if year_text.strip().isdigit() else None
        min_amount = _claim_amount(amount_text) if amount_text.strip() else None

        filtered = filter_opportunities(
            opportunities, status=chosen_status, min_year=min_year, min_amount=min_amount
        )
        if (min_year is not None or min_amount is not None) and len(filtered) < len(
            opportunities
        ):
            st.caption(
                "Las convocatorias sin dato de plazo/importe quedan fuera del filtro "
                "(no se asume que valgan cero)."
            )
        if not filtered:
            st.info("Ninguna convocatoria cumple los filtros.")
        for i, opp in enumerate(filtered):
            title = opp.title.value or "(sin título)"
            with st.expander(f"{status_badge(opp.overall_status)} — {title}", expanded=i == 0):
                for attr, label in _CLAIM_ROWS:
                    claim = getattr(opp, attr)
                    value = claim.value if claim.value is not None else "—"
                    st.markdown(f"**{label}:** {value} · {status_badge(claim.status)}")
                    if claim.sources:
                        urls = " · ".join(ref.url for ref in claim.sources)
                        st.caption(f"Fuente(s): {urls}")
    else:
        st.info("La investigación no encontró convocatorias.")

    if report.unresolved:
        st.subheader("Necesito tu ayuda")
        for u in report.unresolved:
            st.warning(f"**{u.topic}**: {u.reason}\n\n{u.help_needed}")

    if report.failed_sources:
        names = ", ".join(sorted({f.source_name for f in report.failed_sources}))
        st.warning(f"Fuentes con problemas durante la investigación: {names} (R4.4)")
        with st.expander("Detalle de los fallos"):
            for f in report.failed_sources:
                st.text(f"{f.source_name}: {f.error}")

    # Descarga (R7): sin resultados ni incidencias no se ofrece un archivo vacío engañoso.
    if opportunities or report.unresolved or report.failed_sources:
        st.download_button(
            "Descargar informe (Markdown)",
            data=report_to_markdown(report),
            file_name="informe_investigacion.md",
            mime="text/markdown",
            key=f"{key}-download",
        )
    else:
        st.caption("Descarga no disponible: la investigación no produjo contenido (R7.2).")


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
