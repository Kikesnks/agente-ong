"""Serialización de informes de investigación (`ResearchReport` ⇄ dict).

Permite persistir un informe como JSON en `research_runs.report_json` y recargarlo intacto
(R6), preservando la trazabilidad: `Claim.status` (enum por su `value`), las `SourceRef` de
cada dato, `unresolved`, `failed_sources` y las pistas reutilizadas del ledger. Es también la
base de la descarga del informe (R7).

Solo conoce los modelos públicos del investigador; no usa Streamlit ni SQLite.
"""

from __future__ import annotations

from datetime import datetime

from agente_ong.research.models import (
    Claim,
    FailedSource,
    GrantOpportunity,
    LedgerEntry,
    ResearchReport,
    SourceRef,
    StoredResource,
    Unresolved,
    VerificationStatus,
)

# Campos de GrantOpportunity que son Claims (en el orden de presentación del informe).
_OPP_CLAIM_FIELDS = ("title", "organism", "amount", "deadline", "scope", "url")


# --- ResearchReport -> dict ---


def report_to_dict(report: ResearchReport) -> dict:
    """Serializa un `ResearchReport` a un dict apto para JSON (tipos primitivos)."""
    return {
        "mode": report.mode,
        "opportunities": [opp_to_dict(o) for o in report.opportunities],
        "resources": [_resource_to_dict(r) for r in report.resources],
        "ledger": [_ledger_to_dict(e) for e in report.ledger],
        "reused_from_ledger": [_ledger_to_dict(e) for e in report.reused_from_ledger],
        "unresolved": [
            {"topic": u.topic, "reason": u.reason, "help_needed": u.help_needed}
            for u in report.unresolved
        ],
        "failed_sources": [
            {"source_name": f.source_name, "error": f.error} for f in report.failed_sources
        ],
        "filter_verdicts": report.filter_verdicts,
    }


def opp_to_dict(opp: GrantOpportunity) -> dict:
    """Serializa una `GrantOpportunity` sola (pública: reutilizada por llm/enrichment_serde.py
    para serializar discarded/unclassified de un `EnrichedReport`, R7)."""
    data = {name: _claim_to_dict(getattr(opp, name)) for name in _OPP_CLAIM_FIELDS}
    data["overall_status"] = opp.overall_status.value
    data["result_type"] = opp.result_type  # R20
    return data


def _claim_to_dict(claim: Claim) -> dict:
    return {
        "field": claim.field,
        "value": claim.value,
        "status": claim.status.value,
        "is_critical": claim.is_critical,
        "stale": claim.stale,
        "sources": [_ref_to_dict(ref) for ref in claim.sources],
    }


def _ref_to_dict(ref: SourceRef) -> dict:
    return {
        "url": ref.url,
        "source_name": ref.source_name,
        "is_official": ref.is_official,
        "retrieved_at": ref.retrieved_at.isoformat(),
    }


def _ledger_to_dict(entry: LedgerEntry) -> dict:
    return {
        "key": entry.key,
        "kind": entry.kind,
        "outcome": entry.outcome,
        "content_summary": entry.content_summary,
        "topics": list(entry.topics),
        "source_ref": _ref_to_dict(entry.source_ref) if entry.source_ref else None,
        "captured_at": entry.captured_at.isoformat(),
    }


def _resource_to_dict(res: StoredResource) -> dict:
    return {
        "path": res.path,
        "source_url": res.source_url,
        "mode_of_capture": res.mode_of_capture,
        "captured_at": res.captured_at.isoformat(),
        "tags": list(res.tags),
    }


# --- dict -> ResearchReport ---


def report_from_dict(data: dict) -> ResearchReport:
    """Reconstruye un `ResearchReport` desde el dict producido por `report_to_dict`."""
    return ResearchReport(
        mode=data["mode"],
        opportunities=[opp_from_dict(o) for o in data.get("opportunities", [])],
        resources=[_resource_from_dict(r) for r in data.get("resources", [])],
        ledger=[_ledger_from_dict(e) for e in data.get("ledger", [])],
        reused_from_ledger=[_ledger_from_dict(e) for e in data.get("reused_from_ledger", [])],
        unresolved=[
            Unresolved(topic=u["topic"], reason=u["reason"], help_needed=u["help_needed"])
            for u in data.get("unresolved", [])
        ],
        failed_sources=[
            FailedSource(source_name=f["source_name"], error=f["error"])
            for f in data.get("failed_sources", [])
        ],
        filter_verdicts=data.get("filter_verdicts", {}),
    )


def opp_from_dict(data: dict) -> GrantOpportunity:
    """Reconstruye una `GrantOpportunity` sola (pública: contraparte de `opp_to_dict`,
    reutilizada por llm/enrichment_serde.py, R7)."""
    claims = {name: _claim_from_dict(data[name]) for name in _OPP_CLAIM_FIELDS}
    return GrantOpportunity(
        overall_status=VerificationStatus(data["overall_status"]),
        # R20 retrocompatible: los informes persistidos antes de v2 no traen el campo.
        result_type=data.get("result_type", "desconocido"),
        **claims,
    )


def _claim_from_dict(data: dict) -> Claim:
    return Claim(
        field=data["field"],
        value=data["value"],
        status=VerificationStatus(data["status"]),
        is_critical=data["is_critical"],
        stale=data["stale"],
        sources=[_ref_from_dict(ref) for ref in data.get("sources", [])],
    )


def _ref_from_dict(data: dict) -> SourceRef:
    return SourceRef(
        url=data["url"],
        source_name=data["source_name"],
        is_official=data["is_official"],
        retrieved_at=datetime.fromisoformat(data["retrieved_at"]),
    )


def _ledger_from_dict(data: dict) -> LedgerEntry:
    ref = data.get("source_ref")
    return LedgerEntry(
        key=data["key"],
        kind=data["kind"],
        outcome=data["outcome"],
        content_summary=data["content_summary"],
        topics=list(data.get("topics", [])),
        source_ref=_ref_from_dict(ref) if ref else None,
        captured_at=datetime.fromisoformat(data["captured_at"]),
    )


def _resource_from_dict(data: dict) -> StoredResource:
    return StoredResource(
        path=data["path"],
        source_url=data["source_url"],
        mode_of_capture=data["mode_of_capture"],
        captured_at=datetime.fromisoformat(data["captured_at"]),
        tags=list(data.get("tags", [])),
    )


# --- ResearchReport -> Markdown (descarga legible, R7) ---

# Etiquetas legibles de cada estado de verificación (para usuarios no técnicos).
_STATUS_LABELS = {
    VerificationStatus.VERIFIED: "Verificado (2+ fuentes)",
    VerificationStatus.OFFICIAL_UNCROSSED: "Fuente oficial (sin cruzar)",
    VerificationStatus.UNCROSSED_UNVERIFIED: "Sin verificar (1 fuente no oficial)",
    VerificationStatus.CONFLICTING: "Fuentes contradictorias",
    VerificationStatus.NOT_FOUND: "No encontrado",
}

# Nombre legible de cada dato de la convocatoria, en orden de presentación.
_CLAIM_TITLES = {
    "title": "Título",
    "organism": "Organismo",
    "amount": "Importe",
    "deadline": "Plazo",
    "scope": "Ámbito",
    "url": "URL",
}


def opportunity_numbers(report: ResearchReport) -> dict[int, int]:
    """Mapea id(opp) → número (1..N) para las convocatorias accionables (R14).

    Numera en el orden de `report.opportunities` (orden de construcción del investigador,
    preservado por `report_to_dict`/`report_from_dict`). El material informativo
    (`documento_informativo`) no recibe número (R14.4).

    Usa `id()` como clave porque `GrantOpportunity` no es hashable (dataclass con eq=True).
    El mapeo es válido mientras los objetos sean los mismos de `report` —
    `sort_opportunities`, `filter_opportunities` y `partition_by_actionability` devuelven
    listas reordenadas de las MISMAS referencias, nunca copias.
    """
    numbers: dict[int, int] = {}
    n = 0
    for opp in report.opportunities:
        if opp.result_type != "documento_informativo":
            n += 1
            numbers[id(opp)] = n
    return numbers


def report_to_markdown(report: ResearchReport) -> str:
    """Genera el informe en Markdown legible: cada dato con su valor, estado y fuentes."""
    lines: list[str] = ["# Informe de investigación", ""]

    actionable = [o for o in report.opportunities if o.result_type != "documento_informativo"]
    informational = [o for o in report.opportunities if o.result_type == "documento_informativo"]
    numbers = opportunity_numbers(report)

    if actionable:
        lines.append(f"## Convocatorias ({len(actionable)})")
        lines.append("")
        for opp in actionable:
            heading = opp.title.value or "(sin título)"
            lines.append(f"### {numbers[id(opp)]}. {heading}")
            lines.append(f"Estado general: {_status_label(opp.overall_status)}")
            lines.append("")
            for name in _OPP_CLAIM_FIELDS:
                lines.append(_claim_line(_CLAIM_TITLES[name], getattr(opp, name)))
            lines.append("")
    else:
        lines.append("## Convocatorias")
        lines.append("")
        lines.append("No se encontraron convocatorias.")
        lines.append("")

    if informational:
        lines.append("## Material informativo (no convocatorias)")
        lines.append("")
        for opp in informational:
            title = opp.title.value or "(sin título)"
            url = opp.url.value
            lines.append(f"- [{title}]({url})" if url else f"- {title}")
        lines.append("")

    if report.unresolved:
        lines.append("## Datos por confirmar")
        lines.append("")
        for u in report.unresolved:
            lines.append(f"- **{u.topic}**: {u.reason} Ayuda necesaria: {u.help_needed}")
        lines.append("")

    if report.failed_sources:
        lines.append("## Fuentes con problemas")
        lines.append("")
        for f in report.failed_sources:
            lines.append(f"- **{f.source_name}**: {f.error}")
        lines.append("")

    return "\n".join(lines)


def report_to_markdown_summary(report: ResearchReport) -> str:
    """Vista RESUMIDA del informe (R22.1): una ficha breve por convocatoria.

    Por cada convocatoria accionable: título, organismo, importe, plazo, URL y estado de
    verificación — pocas líneas. El material informativo (no convocatorias, R20) se lista
    aparte solo con título y URL. Se genera del mismo informe que la vista detallada (22.4).
    """
    actionable = [o for o in report.opportunities if o.result_type != "documento_informativo"]
    informational = [o for o in report.opportunities if o.result_type == "documento_informativo"]

    lines: list[str] = ["# Informe de investigación (resumen)", ""]
    numbers = opportunity_numbers(report)

    if actionable:
        lines.append(f"## Convocatorias ({len(actionable)})")
        lines.append("")
        for opp in actionable:
            lines.append(f"### {numbers[id(opp)]}. {opp.title.value or '(sin título)'}")
            lines.append(f"- **Organismo**: {_summary_value(opp.organism)}")
            lines.append(f"- **Importe**: {_summary_value(opp.amount)}")
            lines.append(f"- **Plazo**: {_summary_value(opp.deadline)}")
            lines.append(f"- **URL**: {opp.url.value or '—'}{url_verification_suffix(opp.url)}")
            lines.append(f"- **Verificación**: {_status_label(opp.overall_status)}")
            lines.append("")
    else:
        lines.append("## Convocatorias")
        lines.append("")
        lines.append("No se encontraron convocatorias.")
        lines.append("")

    if informational:
        lines.append("## Material informativo (no convocatorias)")
        lines.append("")
        for opp in informational:
            title = opp.title.value or "(sin título)"
            url = opp.url.value
            lines.append(f"- [{title}]({url})" if url else f"- {title}")
        lines.append("")

    if report.unresolved:
        lines.append("## Datos por confirmar")
        lines.append("")
        for u in report.unresolved:
            lines.append(f"- **{u.topic}**: {u.reason}")
        lines.append("")

    if report.failed_sources:
        names = ", ".join(sorted({f.source_name for f in report.failed_sources}))
        lines.append(f"## Fuentes con problemas: {names}")
        lines.append("")

    return "\n".join(lines)


def _summary_value(claim: Claim) -> str:
    """Valor de un claim para la ficha resumida: el dato o '—' si no se encontró."""
    return claim.value if claim.value is not None else "—"


def _status_label(status: VerificationStatus) -> str:
    return _STATUS_LABELS.get(status, status.value)


def format_verification_date(retrieved_at: datetime) -> str:
    """Fecha de consulta en formato DD-MM-AAAA (R15.5)."""
    return retrieved_at.strftime("%d-%m-%Y")


def url_verification_suffix(claim: Claim) -> str:
    """Sufijo '(verificada el DD-MM-AAAA)' para el campo URL; vacío si no hay fuentes (R15.3).

    Solo debe aplicarse al campo url (R15). El borde real es sources == [] — en ese caso
    no hay fecha que mostrar y se devuelve cadena vacía para no añadir texto inútil.
    """
    if not claim.sources:
        return ""
    dates = ", ".join(format_verification_date(ref.retrieved_at) for ref in claim.sources)
    return f" (verificada el {dates})"


def _claim_line(title: str, claim: Claim) -> str:
    """Línea Markdown de un dato: valor, estado de verificación y URLs de sus fuentes."""
    value = claim.value if claim.value is not None else "—"
    if claim.field == "url":
        value += url_verification_suffix(claim)  # R15
    line = f"- **{title}**: {value} · {_status_label(claim.status)}"
    if claim.stale:
        line += " · ⚠ posiblemente desactualizado"
    if claim.sources:
        urls = ", ".join(ref.url for ref in claim.sources)
        line += f" · Fuente(s): {urls}"
    return line
