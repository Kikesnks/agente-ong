"""Smoke E2E de la app Streamlit (`ui/app.py`) con `streamlit.testing.v1.AppTest`.

Valida el cableado extremo a extremo: crear un proyecto desde la sidebar y verlo en la
lista; lanzar una investigación y comprobar que el informe se renderiza ordenado por
fiabilidad y descargable. La lógica fina ya está cubierta por los unit tests; aquí solo el
circuito completo. _Requirements: 1.1, 2.1, 4.1, 11.1_

Inyección de fakes (DECISIONES_PENDIENTES.md #2, opción b): `AppTest` ejecuta la app EN
ESTE MISMO proceso, así que se monkeypatchea `Investigador._default_sources` para que el
JobManager real construya un Investigador real con FUENTES FAKE (tests/research/fakes.py).
Cero llamadas a Tavily/Firecrawl/BDNS/TED. Sin residuos: `RESEARCH_DB_PATH` y el cwd van a
`tmp_path` (la carpeta `RECURSOS/` del proyecto se crea allí) y el singleton del JobManager
se limpia antes y después de cada test.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_ROOT = Path(__file__).resolve().parents[2]
_APP_FILE = _ROOT / "src" / "agente_ong" / "ui" / "app.py"

# Fakes compartidas del investigador (tests/research/ no es un paquete).
sys.path.insert(0, str(_ROOT / "tests" / "research"))
from fakes import FakeFetchSource, FakeSearchSource, make_hit  # noqa: E402

from agente_ong.research.investigador import Investigador  # noqa: E402
from agente_ong.ui import app as app_module  # noqa: E402
from agente_ong.ui.project_store import ProjectStore  # noqa: E402

_TIMEOUT = 30  # segundos (las fakes terminan en milisegundos; margen para CI lentas)

# El form_submit_button no admite key explícita: Streamlit la deriva del form y la label.
_BTN_CREATE = "FormSubmitter:new-project-Crear proyecto"
_BTN_RESEARCH = "FormSubmitter:research-form-Investigar"


@pytest.fixture
def fake_sources() -> list:
    """Dos fuentes de búsqueda + fetch. Regla R14 (investigador-v2): la misma URL cuenta
    una sola vez, así que el informe ordena oficial (bdns) antes que no oficial (tavily)."""
    bdns = FakeSearchSource(
        name="bdns",
        is_official=True,
        hits=[
            make_hit("https://bo.es/c1", source_name="bdns", title="Oficial", is_official=True),
        ],
    )
    tavily = FakeSearchSource(
        name="tavily",
        hits=[make_hit("https://web.example/c3", source_name="tavily", title="Web general")],
    )
    return [bdns, tavily, FakeFetchSource(name="firecrawl")]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_sources: list) -> AppTest:
    """AppTest aislado: db y RECURSOS/ en tmp_path, fuentes fake, singleton limpio."""
    db_path = tmp_path / "agente_ong.db"
    monkeypatch.setenv("RESEARCH_DB_PATH", str(db_path))
    monkeypatch.chdir(tmp_path)  # RECURSOS/ (y cualquier ruta relativa) cae aquí
    monkeypatch.setattr(
        Investigador, "_default_sources", staticmethod(lambda config: fake_sources)
    )
    app_module._job_manager.clear()

    at = AppTest.from_file(str(_APP_FILE), default_timeout=_TIMEOUT)
    at.db_path = db_path  # disponible para los tests
    yield at

    # Apagar el manager del test (la clave del cache es str(config.db_path)).
    app_module._job_manager(str(db_path)).shutdown(wait=False)
    app_module._job_manager.clear()


def _create_project(at: AppTest, name: str = "ONG Smoke") -> None:
    at.text_input(key="new-project-name").set_value(name)
    at.text_area(key="new-project-objective").set_value("Conseguir financiación")
    at.text_input(key="new-project-terms").set_value("cultura")
    at.button(key=_BTN_CREATE).click().run()
    assert not at.exception, at.exception[0].value


def _wait_for_finished_run(db_path: Path, project_id: int = 1) -> str:
    """Espera (con timeout) a que el run del proyecto quede persistido como terminado."""
    deadline = time.time() + _TIMEOUT
    while time.time() < deadline:
        with ProjectStore(db_path) as store:
            runs = store.list_runs(project_id)
            if runs and runs[0].status != "running":
                return runs[0].status
        time.sleep(0.05)
    raise AssertionError("la investigación no terminó dentro del timeout")


# --- Crear proyecto y verlo en la lista (R1.1) ---


def test_create_project_appears_in_sidebar_and_creates_folder(app: AppTest, tmp_path: Path) -> None:
    app.run()
    assert not app.exception
    _create_project(app, "ONG Smoke")

    # El proyecto queda seleccionado, listado en la sidebar y con su vista abierta.
    assert app.title[0].value == "ONG Smoke"
    sidebar_radio = app.radio(key="sidebar-projects")
    assert sidebar_radio.value == 1  # id del proyecto en la lista
    # Su carpeta de documentos existe bajo el RECURSOS/ del test (no el real).
    assert (tmp_path / "RECURSOS" / "ONG Smoke").is_dir()


# --- Investigación E2E con fakes: informe ordenado y descargable (R2.1, R4.1, R11.1) ---


def test_research_flow_renders_sorted_report(app: AppTest, fake_sources: list) -> None:
    app.run()
    _create_project(app)

    # Lanzar con los defaults del formulario (términos prellenados del proyecto).
    app.button(key=_BTN_RESEARCH).click().run()
    assert not app.exception, app.exception[0].value

    status = _wait_for_finished_run(app.db_path)
    assert status == "done"
    # Las fuentes consultadas fueron las FAKE (ninguna API real).
    assert fake_sources[0].search_calls, "la fuente fake oficial debe haberse consultado"

    app.run()  # rerun: la UI recoge el run persistido y renderiza el informe
    assert not app.exception, app.exception[0].value

    # La convocatoria accionable (BDNS, oficial) se renderiza como expander con su estado.
    labels = [e.label for e in app.expander if "—" in str(e.label)]
    assert len(labels) == 1
    assert "Oficial" in labels[0] and "oficial (sin cruzar)" in labels[0]

    # R20.2: el resultado de Tavily sin señal de convocatoria va a "Material informativo"
    # (sección aparte, no como convocatoria accionable).
    subheaders = " ".join(str(s.value) for s in app.subheader)
    assert "Material informativo" in subheaders
    all_md = " ".join(str(m.value) for m in app.markdown)
    assert "Web general" in all_md

    # Descarga del informe disponible (R7.1).
    assert len(app.get("download_button")) == 1
