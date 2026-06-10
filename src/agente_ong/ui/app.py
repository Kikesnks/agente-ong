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

from agente_ong.research.config import DEFAULT_DB_PATH, ResearchConfig
from agente_ong.ui import uploads
from agente_ong.ui.models import Project
from agente_ong.ui.project_store import ProjectStore

_SELECTED_KEY = "selected_project_id"


def _base_config() -> ResearchConfig:
    """Config base desde el entorno; la UI exige persistencia (db_path nunca None)."""
    config = ResearchConfig.from_env()
    if config.db_path is None:
        config.db_path = DEFAULT_DB_PATH
    return config


def _create_project(store: ProjectStore, name: str, objective: str, terms_raw: str) -> Project:
    """Valida el nombre, crea el proyecto y su carpeta `RECURSOS/[nombre]/` (R1.4/R12.4).

    Orden deliberado: primero la validación del nombre como carpeta (`project_dir`), luego
    el INSERT (UNIQUE) y solo después el mkdir — un nombre inválido o duplicado no deja ni
    fila ni carpeta a medias.
    """
    directory = uploads.project_dir(name)  # valida; lanza UploadError si no es válido
    terms = [t.strip() for t in terms_raw.split(",") if t.strip()]
    project = store.create_project(name.strip(), objective.strip(), terms)
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
        if st.form_submit_button("Crear proyecto"):
            try:
                project = _create_project(store, name, objective, terms)
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
    """Vista del proyecto seleccionado (investigación y documentos: tareas 29 y 30)."""
    st.title(project.name)
    if project.objective:
        st.markdown(project.objective)
    if project.search_terms:
        st.caption("Términos de búsqueda: " + ", ".join(project.search_terms))


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
