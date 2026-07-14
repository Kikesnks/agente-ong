"""Test end-to-end de la mini-spec `descartados-filtro` (T7): los 4 orígenes de descarte,
el caso sin descartes, la retrocompatibilidad del serde y la coincidencia entre las 3 vistas
(R9.4) que consumen `filter_verdicts`.

Aislado de `test_jobs.py` (ciclo de vida genérico del `JobManager`) porque este archivo
compone el flujo completo `_run_job_inner` → `enrich_report` → `classify_report` →
`classify_result` con un proveedor LLM secuenciado real (no mockea `enrich_report` como sí
hace `test_jobs.py` en sus tests de cableado): es la única cobertura del pipeline íntegro,
así que merece vivir en su propio archivo con nombre trazable a la spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agente_ong.llm.errors import LLMConnectionError
from agente_ong.llm.provider import LLMProvider, LLMResponse
from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import Claim, GrantOpportunity, ResearchReport, ResearchRequest
from agente_ong.research.ods_catalogo import OdsEntry
from agente_ong.ui.jobs import JobManager
from agente_ong.ui.project_store import ProjectStore
from agente_ong.ui.report_serde import (
    DISCARD_LABELS,
    classify_for_display,
    partition_by_discard_status,
    report_from_dict,
    report_to_markdown,
    report_to_markdown_summary,
)

_TIMEOUT = 10  # segundos; los fakes terminan en milisegundos
_SELECTED_ODS: list[OdsEntry] = [{"numero": 1, "nombre": "Fin de la pobreza"}]


@dataclass
class _SequenceLLMProvider(LLMProvider):
    """Doble LOCAL (mismo patrón que `tests/llm/test_filter_report.py`/`test_enrichment.py`):
    una respuesta (texto) o excepción distinta por llamada, en el orden en que
    `classify_report` recorre `report.opportunities`."""

    outcomes: list[str | BaseException]
    calls: int = field(default=0, init=False)

    def complete(self, system: str, user: str) -> LLMResponse:
        item = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        return LLMResponse(text=item, input_tokens=0, output_tokens=0)


class FakeInvestigador:
    """Doble del `Investigador`: context manager que devuelve un informe fijo."""

    def __init__(self, report: ResearchReport) -> None:
        self._report = report

    def __enter__(self) -> "FakeInvestigador":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def run(self, request: ResearchRequest, selected_ods: list[OdsEntry]) -> ResearchReport:
        return self._report


def _opportunity(title_value: str, *, result_type: str = "convocatoria_probable") -> GrantOpportunity:
    def claim(field_name: str, value: str | None = None) -> Claim:
        return Claim(field=field_name, value=value)

    return GrantOpportunity(
        title=claim("titulo", title_value),
        organism=claim("organismo"),
        amount=claim("importe"),
        deadline=claim("plazo"),
        scope=claim("ambito"),
        url=claim("url", f"https://example.org/{title_value}"),
        result_type=result_type,
    )


def _wait(manager: JobManager, job_id: str) -> None:
    manager.get_job(job_id).future.result(timeout=_TIMEOUT)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agente_ong.db"


@pytest.fixture
def project_id(db_path: Path) -> int:
    with ProjectStore(db_path) as store:
        return store.create_project("ONG").id


def _request() -> ResearchRequest:
    return ResearchRequest(mode="calls")


def _config() -> ResearchConfig:
    return ResearchConfig(db_path=None)


def _submit_and_wait(
    db_path: Path, project_id: int, report: ResearchReport
) -> tuple[JobManager, dict]:
    """Lanza un job con `report` fijo y devuelve `(manager, run.report persistido)`.

    El caller es responsable de `manager.shutdown()`.
    """
    fake = FakeInvestigador(report)
    manager = JobManager(db_path, investigador_factory=lambda cfg: fake)
    job_id = manager.submit(project_id, _config(), _request(), _SELECTED_ODS)
    _wait(manager, job_id)
    assert manager.status(job_id) == "done"
    with ProjectStore(db_path) as store:
        persisted = store.list_runs(project_id)[0].report
    return manager, persisted


# --- Escenario 1: los 4 orígenes de descarte end-to-end (R3/R8) ---


def test_end_to_end_covers_all_four_discard_origins(
    db_path: Path, project_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = _opportunity("activa")
    discarded_filtro = _opportunity("descartada")
    no_clasificada_provider = _opportunity("fallo_proveedor")
    no_clasificada_response = _opportunity("respuesta_rara")
    informativo = _opportunity("informativo", result_type="documento_informativo")
    report = ResearchReport(
        mode="calls",
        opportunities=[
            active,
            discarded_filtro,
            no_clasificada_provider,
            no_clasificada_response,
            informativo,
        ],
    )

    provider = _SequenceLLMProvider(
        outcomes=[
            "SI",  # activa
            "NO",  # descartada por filtro
            LLMConnectionError("fallo simulado"),  # no_clasificada_provider
            "esto no es SI ni NO",  # no_clasificada_response
            "SI",  # informativo: la heurística (R20) gana pese al veredicto "si"
        ]
    )
    monkeypatch.setattr("agente_ong.ui.jobs.is_ollama_available", lambda *a, **kw: True)
    monkeypatch.setattr("agente_ong.ui.jobs.OllamaProvider", lambda **kw: provider)

    manager, persisted = _submit_and_wait(db_path, project_id, report)
    try:
        restored = report_from_dict(persisted)
        by_title = {o.title.value: o for o in restored.opportunities}

        expected = {
            "activa": "activa",
            "descartada": "descartada_filtro",
            "fallo_proveedor": "no_clasificada_provider",
            "respuesta_rara": "no_clasificada_response",
            "informativo": "documento_informativo",
        }
        for title, expected_status in expected.items():
            actual = classify_for_display(by_title[title], restored.filter_verdicts)
            assert actual == expected_status, f"{title}: esperado {expected_status}, fue {actual}"
    finally:
        manager.shutdown()


# --- Escenario 2: sin Ollama disponible (R7.3) ---


def test_end_to_end_without_ollama_still_discards_documento_informativo(
    db_path: Path, project_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agente_ong.ui.jobs.is_ollama_available", lambda *a, **kw: False)

    active = _opportunity("activa")
    informativo = _opportunity("informativo", result_type="documento_informativo")
    report = ResearchReport(mode="calls", opportunities=[active, informativo])

    manager, persisted = _submit_and_wait(db_path, project_id, report)
    try:
        restored = report_from_dict(persisted)
        assert restored.filter_verdicts == {}  # sin provider, no hay veredictos que aplicar

        by_title = {o.title.value: o for o in restored.opportunities}
        assert classify_for_display(by_title["activa"], restored.filter_verdicts) == "activa"
        assert (
            classify_for_display(by_title["informativo"], restored.filter_verdicts)
            == "documento_informativo"
        )
    finally:
        manager.shutdown()


# --- Escenario 3: sin descartes (R4.2/R5.2) ---


def test_no_discards_produces_empty_bucket_and_no_markdown_section() -> None:
    con_veredicto_si = _opportunity("con_veredicto")
    sin_veredicto = _opportunity("sin_veredicto")
    report = ResearchReport(
        mode="calls",
        opportunities=[con_veredicto_si, sin_veredicto],
        filter_verdicts={"https://example.org/con_veredicto": "si"},
    )

    active, discarded = partition_by_discard_status(report.opportunities, report.filter_verdicts)
    assert active == [con_veredicto_si, sin_veredicto]
    assert discarded == []

    assert "## Descartados" not in report_to_markdown(report)
    assert "## Descartados" not in report_to_markdown_summary(report)


# --- Escenario 4: coincidencia entre las 3 vistas (R9.4) ---


def _parse_descartados_section(markdown: str) -> list[tuple[str, str]]:
    """Extrae (título, etiqueta) de la sección "## Descartados" de un informe Markdown, en
    el orden en que aparecen las líneas `- entrada — etiqueta`."""
    lines = markdown.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("## Descartados"))
    except StopIteration:
        return []
    entries: list[tuple[str, str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if not line.startswith("- "):
            continue
        entry, _, label = line[2:].partition(" — ")
        if entry.startswith("[") and "](" in entry:
            title = entry[1 : entry.index("](")]
        else:
            title = entry
        entries.append((title, label))
    return entries


def test_three_views_agree_on_discarded_opportunities_and_labels() -> None:
    active = _opportunity("activa")
    discarded_filtro = _opportunity("descartada")
    no_clasificada_provider = _opportunity("fallo_proveedor")
    no_clasificada_response = _opportunity("respuesta_rara")
    informativo = _opportunity("informativo", result_type="documento_informativo")
    report = ResearchReport(
        mode="calls",
        opportunities=[
            active,
            discarded_filtro,
            no_clasificada_provider,
            no_clasificada_response,
            informativo,
        ],
        filter_verdicts={
            "https://example.org/activa": "si",
            "https://example.org/descartada": "no",
            "https://example.org/fallo_proveedor": "no_clasificado_provider",
            "https://example.org/respuesta_rara": "no_clasificado_response",
        },
    )

    # Vista 1 y 2: Markdown resumido y detallado.
    from_summary = _parse_descartados_section(report_to_markdown_summary(report))
    from_detail = _parse_descartados_section(report_to_markdown(report))

    # Vista 3 (Streamlit): render_report consume exactamente este mismo bucket para
    # construir el expandible "DESCARTADOS: N" (ver ui/report_view.py::render_report) — se
    # verifica el bucket compartido en vez de renderizar Streamlit real.
    # R9.4 cubierto vía función clasificadora compartida; smoke test AppTest fuera de
    # alcance por coste (T6 ya cubrió con un mock ligero que el título del expander usa
    # este mismo `len(discarded)`; aquí se cierra el círculo de que el CONTENIDO coincide).
    _, discarded = partition_by_discard_status(report.opportunities, report.filter_verdicts)
    from_render = [(opp.title.value, DISCARD_LABELS[status]) for opp, status in discarded]

    expected = [
        ("descartada", "Descartada por filtro semántico"),
        ("fallo_proveedor", "No clasificada (fallo del proveedor LLM)"),
        ("respuesta_rara", "No clasificada (respuesta inesperada del LLM)"),
        ("informativo", "Documento informativo (heurística)"),
    ]
    assert from_summary == expected
    assert from_detail == expected
    assert from_render == expected
