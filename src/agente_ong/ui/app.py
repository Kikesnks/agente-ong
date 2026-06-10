"""App Streamlit del agente ONG.

Punto de arranque de la interfaz:

    streamlit run src/agente_ong/ui/app.py

Navegación: sidebar con la lista de proyectos y el formulario de alta (R1/R12); a la
derecha, la vista del proyecto seleccionado. La configuración base sale del entorno
(`ResearchConfig.from_env()`): las claves de API nunca se muestran ni se piden en la UI.

El `ProjectStore` se abre y cierra EN CADA rerun del script (conexión del hilo de script);
los hilos de fondo del `JobManager` abren las suyas propias (ver jobs.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from agente_ong.research.config import DEFAULT_DB_PATH, ResearchConfig
from agente_ong.ui import request_builder, uploads
from agente_ong.ui.jobs import JobManager
from agente_ong.ui.models import Project
from agente_ong.ui.project_store import ProjectStore
from agente_ong.ui.report_serde import report_from_dict
from agente_ong.ui.report_view import render_report

_SELECTED_KEY = "selected_project_id"

# Intervalo de sondeo del estado de los jobs mientras hay investigaciones activas (R2.2).
_POLL_MS = 2000

# Fuentes que la UI ofrece activar/desactivar (R9.2). Espeja las que construye
# Investigador._default_sources; la UI solo conoce el NOMBRE y una etiqueta legible.
_SOURCE_LABELS = {
    "bdns": "BDNS — subvenciones de España (oficial)",
    "ted": "TED — licitaciones de la UE (oficial)",
    "tavily": "Búsqueda web (Tavily)",
    "firecrawl": "Lectura de páginas y URLs directas (Firecrawl)",
}

# Niveles de profundidad en lenguaje sencillo, sin exponer los números internos (R8.4).
_DEPTH_LABELS = {
    "rápida": "rápida — un vistazo veloz, menos cobertura",
    "normal": "normal — equilibrio entre tiempo y cobertura (recomendada)",
    "exhaustiva": "exhaustiva — más fuentes y enlaces, tarda más",
}


@st.cache_resource
def _job_manager(db_path: str) -> JobManager:
    """Singleton de proceso: sobrevive a los reruns; los workers abren sus conexiones."""
    return JobManager(db_path)


def _base_config() -> ResearchConfig:
    """Config base desde el entorno; la UI exige persistencia (db_path nunca None)."""
    config = ResearchConfig.from_env()
    if config.db_path is None:
        config.db_path = DEFAULT_DB_PATH
    return config


def _create_project(
    store: ProjectStore, name: str, objective: str, terms_raw: str, search_context: str
) -> Project:
    """Valida el nombre, crea el proyecto y su carpeta `RECURSOS/[nombre]/` (R1.4/R12.4).

    Orden deliberado: primero la validación del nombre como carpeta (`project_dir`), luego
    el INSERT (UNIQUE) y solo después el mkdir — un nombre inválido o duplicado no deja ni
    fila ni carpeta a medias.
    """
    directory = uploads.project_dir(name)  # valida; lanza UploadError si no es válido
    terms = [t.strip() for t in terms_raw.split(",") if t.strip()]
    project = store.create_project(name.strip(), objective.strip(), terms, search_context)
    directory.mkdir(parents=True, exist_ok=True)
    return project


def _sidebar(store: ProjectStore) -> Project | None:
    """Lista + alta de proyectos en la sidebar; devuelve el proyecto seleccionado."""
    st.sidebar.title("Agente ONG")

    projects = store.list_projects()
    selected: Project | None = None
    if projects:
        ids = [p.id for p in projects]
        by_id = {p.id: p for p in projects}
        current = st.session_state.get(_SELECTED_KEY)
        index = ids.index(current) if current in ids else 0
        chosen = st.sidebar.radio(
            "Proyectos",
            ids,
            index=index,
            format_func=lambda pid: by_id[pid].name,
            key="sidebar-projects",
        )
        st.session_state[_SELECTED_KEY] = chosen
        selected = by_id[chosen]
    else:
        st.sidebar.info("Aún no hay proyectos. Crea el primero aquí debajo.")

    with st.sidebar.form("new-project", clear_on_submit=True):
        st.subheader("Nuevo proyecto")
        name = st.text_input("Nombre", key="new-project-name")
        objective = st.text_area("Objetivo", key="new-project-objective")
        terms = st.text_input(
            "Términos de búsqueda (separados por comas)", key="new-project-terms"
        )
        context = st.text_input(
            "¿Qué tipo de organización sois y cuál es vuestro ámbito? (opcional)",
            placeholder='p.ej. "fundación cultural en Andalucía" o "ONG de cooperación internacional"',
            key="new-project-context",
        )
        if st.form_submit_button("Crear proyecto"):
            try:
                project = _create_project(store, name, objective, terms, context)
            except uploads.UploadError as exc:
                st.sidebar.error(str(exc))
            except ValueError as exc:
                st.sidebar.error(str(exc))
            except sqlite3.IntegrityError:
                st.sidebar.error(f"Ya existe un proyecto con el nombre {name.strip()!r}.")
            else:
                st.session_state[_SELECTED_KEY] = project.id
                st.rerun()
    return selected


def _project_view(store: ProjectStore, config: ResearchConfig, project: Project) -> None:
    """Vista del proyecto seleccionado: investigación (R2/R8-R11) y documentos (R3)."""
    st.title(project.name)
    if project.objective:
        st.markdown(project.objective)
    if project.search_terms:
        st.caption("Términos de búsqueda: " + ", ".join(project.search_terms))

    manager = _job_manager(str(config.db_path))
    research_tab, docs_tab = st.tabs(["Investigación", "Documentos"])
    with research_tab:
        _research_form(config, project, manager)
        _research_status(store, project, manager)
    with docs_tab:
        _documents_panel(project)


def _research_form(config: ResearchConfig, project: Project, manager: JobManager) -> None:
    """Controles de lanzamiento: términos, nivel (R8), fuentes y URLs (R9), año (R10)."""
    with st.form("research-form"):
        st.subheader("Nueva investigación")
        terms_raw = st.text_input(
            "Términos de búsqueda (separados por comas)",
            value=", ".join(project.search_terms),
            key="research-terms",
        )
        level = st.radio(
            "Nivel de profundidad",
            list(_DEPTH_LABELS),
            index=list(_DEPTH_LABELS).index(request_builder.DEFAULT_DEPTH_LEVEL),
            format_func=_DEPTH_LABELS.get,
            key="research-depth",
        )
        sources = st.multiselect(
            "Fuentes activas",
            list(_SOURCE_LABELS),
            default=list(_SOURCE_LABELS),
            format_func=_SOURCE_LABELS.get,
            key="research-sources",
        )
        urls_raw = st.text_area(
            "URLs directas a leer (una por línea, opcional)", key="research-urls"
        )
        min_year = st.number_input(
            "Año mínimo de las convocatorias (opcional)",
            min_value=2000,
            max_value=2100,
            value=None,
            step=1,
            key="research-min-year",
        )
        if st.form_submit_button("Investigar"):
            terms = [t.strip() for t in terms_raw.split(",") if t.strip()]
            direct_urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
            try:
                job_config, request = request_builder.build(
                    config,
                    terms=terms,
                    depth_level=level,
                    min_year=int(min_year) if min_year else None,
                    enabled_sources=set(sources),
                    direct_urls=direct_urls,
                    # R13: el contexto se hereda del proyecto; vacío => default en build().
                    search_context=project.search_context,
                )
            except ValueError as exc:  # p.ej. sin fuentes ni URLs (R9.5)
                st.error(str(exc))
            else:
                manager.submit(project.id, job_config, request)
                st.rerun()


def _research_status(store: ProjectStore, project: Project, manager: JobManager) -> None:
    """Estado de los jobs y resultados persistidos; refresca mientras haya jobs vivos."""
    active = [j for j in manager.active_jobs() if j.project_id == project.id]
    if active:
        # Sondeo periódico SOLO mientras hay trabajo en curso (R2.2); los hilos de fondo
        # nunca tocan st.*: este rerun es quien lee su estado.
        st_autorefresh(interval=_POLL_MS, key="jobs-poll")
        st.info(f"🔎 {len(active)} investigación(es) en curso… esta vista se actualiza sola.")

    runs = store.list_runs(project.id)
    if not runs and not active:
        st.caption("Este proyecto aún no tiene investigaciones.")
        return
    for run in runs:
        started = run.created_at.strftime("%d/%m/%Y %H:%M")
        if run.status == "running":
            continue  # ya representado por el aviso de "en curso"
        if run.status == "error":
            st.error(f"La investigación del {started} falló: {run.error}. Puedes reintentar.")
            continue
        with st.container(border=True):
            st.markdown(f"**Informe del {started}**")
            if run.params.get("query_terms"):
                st.caption("Búsqueda: " + ", ".join(run.params["query_terms"]))
            render_report(report_from_dict(run.report), key=f"run-{run.id}")


def _documents_panel(project: Project) -> None:
    """Subir, listar y borrar documentos del proyecto bajo `RECURSOS/[nombre]/` (R3)."""
    st.subheader("Documentos del proyecto")
    mb = uploads.MAX_UPLOAD_BYTES // (1024 * 1024)
    allowed = ", ".join(sorted(e.upper() for e in uploads.ALLOWED_EXT))
    st.caption(f"Tipos admitidos: {allowed}. Tamaño máximo: {mb} MB por archivo.")

    uploaded = st.file_uploader(
        "Subir documentos",
        type=sorted(uploads.ALLOWED_EXT),
        accept_multiple_files=True,
        key=f"docs-uploader-{project.id}",
    )
    # Streamlit reenvía los archivos en cada rerun: se registra lo ya guardado para no
    # duplicarlo (el renombrado automático convertiría cada rerun en una copia nueva).
    saved_key = f"docs-saved-{project.id}"
    already_saved: set[str] = st.session_state.setdefault(saved_key, set())
    for file in uploaded or []:
        file_id = f"{file.file_id}"
        if file_id in already_saved:
            continue
        try:
            target = uploads.save_upload(project.name, file.name, file.getvalue())
        except uploads.UploadError as exc:
            st.error(f"{file.name}: {exc}")
        else:
            already_saved.add(file_id)
            if target.name != file.name:
                st.info(f"Ya existía {file.name!r}: guardado como {target.name!r}.")

    documents = uploads.list_documents(project.name)
    if not documents:
        st.caption("Este proyecto aún no tiene documentos.")
        return
    for doc in documents:
        col_name, col_del = st.columns([5, 1])
        col_name.markdown(f"📄 {doc.name}")
        if col_del.button("Borrar", key=f"doc-del-{project.id}-{doc.name}"):
            try:
                uploads.delete_document(project.name, doc.name)
            except uploads.UploadError as exc:
                st.error(str(exc))
            else:
                st.rerun()


def main() -> None:
    st.set_page_config(page_title="Agente ONG", layout="wide")
    config = _base_config()
    with ProjectStore(Path(config.db_path)) as store:
        project = _sidebar(store)
        if project is None:
            st.markdown(
                "Crea un proyecto en la barra lateral para empezar: cada proyecto agrupa "
                "el objetivo de tu ONG, sus documentos y sus investigaciones."
            )
            return
        _project_view(store, config, project)


# Tanto `streamlit run` como AppTest ejecutan el script como "__main__"; el import del
# módulo (tests unitarios) no arranca la app.
if __name__ == "__main__":
    main()
