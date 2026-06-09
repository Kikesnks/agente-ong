"""Capa de interfaz Streamlit del agente ONG.

Pone el módulo investigador (`agente_ong.research`) en manos de usuarios no técnicos:
gestión de proyectos persistidos en SQLite (`project_store`), ejecución asíncrona de
investigaciones en hilos de fondo (`jobs`), serialización y descarga de informes
(`report_serde`), presentación ordenada y filtrable (`report_view`), mapeo de controles de
UI a config+request (`request_builder`), subida de documentos del proyecto (`uploads`) y la
app Streamlit (`app`).

La UI consume el investigador solo por su interfaz pública (fachada `Investigador`); el
núcleo permanece portable y sin dependencias de esta capa.
"""
