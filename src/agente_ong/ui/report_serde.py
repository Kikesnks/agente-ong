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
        "opportunities": [_opp_to_dict(o) for o in report.opportunities],
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
    }


def _opp_to_dict(opp: GrantOpportunity) -> dict:
    data = {name: _claim_to_dict(getattr(opp, name)) for name in _OPP_CLAIM_FIELDS}
    data["overall_status"] = opp.overall_status.value
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
        opportunities=[_opp_from_dict(o) for o in data.get("opportunities", [])],
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
    )


def _opp_from_dict(data: dict) -> GrantOpportunity:
    claims = {name: _claim_from_dict(data[name]) for name in _OPP_CLAIM_FIELDS}
    return GrantOpportunity(
        overall_status=VerificationStatus(data["overall_status"]), **claims
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
