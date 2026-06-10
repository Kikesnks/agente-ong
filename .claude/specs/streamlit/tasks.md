# Implementation Plan — Interfaz Streamlit

## Task Overview

Implementación en dos bloques. **Bloque A**: extensiones mínimas y retrocompatibles del módulo
investigador (`src/agente_ong/research/`) que habilitan los controles de la UI —activar/desactivar
fuentes y URL directa (R9), filtro temporal `min_year` extendido a BDNS (R10)— sin tocar la firma
estable de `TedSource`; la profundidad (R8) ya está cubierta por los overrides existentes de
`ResearchRequest`. **Bloque B**: la capa de UI nueva (`src/agente_ong/ui/`): stores de proyectos en
SQLite, ejecución asíncrona en hilos de fondo, serialización de informes, mapeo de controles,
render con orden/filtros, subida de documentos y la app Streamlit. Cada bloque de código va con su
test, y se cierra con un smoke E2E.

## Steering Document Compliance

Las tareas respetan `structure.md` (paquete `ui/` bajo `src/agente_ong/`, tests espejo en
`tests/ui/`, documentos del humano solo bajo `RECURSOS/[nombre_proyecto]/`) y `tech.md` (Streamlit
como UI, SQLite stdlib como persistencia en el mismo `.db`, abstracción de fuentes intacta, claves
solo por entorno). El investigador permanece portable: la UI lo consume por su interfaz pública y
solo se le añaden campos opcionales con default que preserva el comportamiento actual.

## Atomic Task Requirements

Cada tarea toca 1-3 archivos, es completable en 15-30 min, tiene un único resultado testeable y
especifica los archivos exactos.

## Tasks

### Bloque A — Extensiones del módulo investigador (R8/R9/R10)

- [x] 1. Añadir enabled_sources y direct_urls a ResearchRequest en models.py
  - File: src/agente_ong/research/models.py
  - Añadir a `ResearchRequest` dos campos opcionales: `enabled_sources: set[str] | None = None`
    (None = todas las fuentes) y `direct_urls: list[str] = field(default_factory=list)`
  - Purpose: permitir a la UI elegir fuentes y aportar URLs directas por investigación
  - _Leverage: src/agente_ong/research/models.py (ResearchRequest existente)_
  - _Requirements: 9.1, 9.2_

- [x] 2. Filtrar fuentes por enabled_sources en ResearchGraph (graph.py)
  - File: src/agente_ong/research/graph.py
  - En `search()` y `read_deep()`, filtrar `self._sources` por `request.enabled_sources` (match
    por `source.name`) cuando no sea None; si es None, comportamiento actual
  - Purpose: respetar la activación/desactivación de fuentes (R9.2/R9.3)
  - _Leverage: src/agente_ong/research/sources/base.py (SearchSource.name/supports)_
  - _Requirements: 9.2, 9.3_

- [x] 3. Sembrar la frontera de read_deep con direct_urls (graph.py)
  - File: src/agente_ong/research/graph.py (continúa de la tarea 2)
  - En `read_deep()`, añadir las `request.direct_urls` a la frontera en el nivel 1 (junto a los
    hits), respetando ledger y `DepthLimiter`; deben leerse con Firecrawl aunque no haya búsqueda
  - Purpose: lectura directa de URLs indicadas por el usuario (R9.1/R9.4)
  - _Leverage: src/agente_ong/research/graph.py (read_deep, frontier)_
  - _Requirements: 9.1, 9.4_

- [x] 4. Test de enabled_sources y direct_urls en test_graph_flow.py
  - File: tests/research/test_graph_flow.py
  - Casos: investigación con un subconjunto de fuentes solo usa esas; URL directa se lee aun sin
    hits de búsqueda; ambas fuentes desactivadas + URL directa => se lee la URL
  - Purpose: garantizar el filtrado de fuentes y la siembra de URLs directas
  - _Leverage: tests/research/fakes.py (FakeSearchSource, FakeFetchSource, make_hit)_
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 5. Añadir min_year a ResearchConfig en config.py
  - File: src/agente_ong/research/config.py
  - Campo `min_year: int | None = None` y lectura de `RESEARCH_MIN_YEAR` en `from_env()` (entero
    opcional, usando el helper `_env_int` o variante que admita None)
  - Purpose: configurar el filtro temporal a nivel de investigación (R10)
  - _Leverage: src/agente_ong/research/config.py (from_env, _env_int)_
  - _Requirements: 10.1_

- [x] 6. Construir fuentes con min_year en _default_sources (investigador.py)
  - File: src/agente_ong/research/investigador.py
  - `TedSource(config, min_year=config.min_year or (datetime.now().year - 1))` (preserva el
    default actual) y `BdnsSource(config, min_year=config.min_year)` (None = sin filtro)
  - Purpose: propagar el año mínimo a las fuentes oficiales que lo soportan
  - _Leverage: src/agente_ong/research/sources/ted.py (min_year ya existente)_
  - _Requirements: 10.1, 10.4_

- [x] 7. Añadir min_year a BdnsSource verificando el formato de fechaRecepcion (bdns.py)
  - File: src/agente_ong/research/sources/bdns.py
  - PRIMERO: confirmar con UNA llamada en vivo el formato real de `fechaRecepcion` (mismo método
    de verificación usado al integrar BDNS). Luego: añadir `min_year: int | None = None` al
    constructor; en `_to_hits`, descartar convocatorias cuyo año de `fechaRecepcion` sea < min_year;
    conservar los hits sin fecha parseable (no inventar antigüedad)
  - Purpose: extender el filtro temporal a BDNS de forma coherente con TED (R10.2)
  - _Leverage: src/agente_ong/research/sources/ted.py (patrón de min_year)_
  - _Requirements: 10.1, 10.2_

- [x] 8. Test de BdnsSource.min_year en test_sources.py
  - File: tests/research/test_sources.py
  - Casos: descarta convocatoria con año < min_year; conserva la de año >= min_year; conserva la
    que no trae fecha; `min_year=None` no filtra (sin cambios)
  - Purpose: blindar el filtro temporal de BDNS
  - _Leverage: tests/research/test_sources.py (_FakeHttp)_
  - _Requirements: 10.2, 10.3_

### Bloque B — Capa de interfaz (src/agente_ong/ui/)

- [x] 9. Crear scaffolding del paquete ui en ui/__init__.py
  - File: src/agente_ong/ui/__init__.py
  - Paquete Python con docstring de módulo (capa de UI Streamlit)
  - Purpose: establecer la estructura importable de la UI
  - _Requirements: 1.1_

- [x] 10. Definir modelos de UI en ui/models.py
  - File: src/agente_ong/ui/models.py
  - Dataclasses `Project` (id, name, objective, search_terms, created_at), `ResearchRun` (id,
    project_id, status, created_at, finished_at, params, report, error) y `Job` (id, project_id,
    status, future, run_id); alias `JobStatus`/`RunStatus` como Literals
  - Purpose: tipos de la capa de UI para proyectos, runs y jobs
  - _Leverage: src/agente_ong/research/models.py (estilo dataclass)_
  - _Requirements: 12.1_

- [x] 11. Implementar report_to_dict / report_from_dict en ui/report_serde.py
  - File: src/agente_ong/ui/report_serde.py
  - Serializar/deserializar `ResearchReport` ⇄ dict preservando `GrantOpportunity`, `Claim.status`
    (enum por value), `SourceRef`, `unresolved`, `failed_sources`, `reused_from_ledger`
  - Purpose: persistir y recargar informes (R6) y base de la descarga (R7)
  - _Leverage: src/agente_ong/research/models.py (ResearchReport, Claim, SourceRef)_
  - _Requirements: 6.2, 7.1_

- [x] 12. Implementar report_to_markdown en ui/report_serde.py
  - File: src/agente_ong/ui/report_serde.py (continúa de la tarea 11)
  - Generar Markdown legible del informe: por convocatoria, cada dato con su valor, estado de
    verificación y URL de fuente; secciones de `unresolved` y `failed_sources`
  - Purpose: descarga del informe en Markdown (R7.1)
  - _Leverage: src/agente_ong/research/models.py (VerificationStatus)_
  - _Requirements: 7.1, 7.2_

- [x] 13. Test de report_serde en tests/ui/test_report_serde.py
  - File: tests/ui/test_report_serde.py
  - Round-trip dict (igualdad de estados/fuentes/listas) y que el Markdown incluye fuente y estado
  - Purpose: garantizar persistencia fiel y descarga correcta
  - _Leverage: src/agente_ong/research/models.py (construir un ResearchReport de ejemplo)_
  - _Requirements: 7.1, 6.2_

- [x] 14. Crear ProjectStore con esquema y CRUD de projects en ui/project_store.py
  - File: src/agente_ong/ui/project_store.py
  - Conexión SQLite propia (WAL, foreign_keys=ON, consultas parametrizadas) al mismo `db_path`;
    `CREATE TABLE IF NOT EXISTS projects/research_runs` + índice; `create_project`, `list_projects`,
    `get_project` con `UNIQUE(name)`
  - Purpose: persistir y listar proyectos en el `.db` del producto (R12.2/R12.3)
  - _Leverage: src/agente_ong/research/store/sqlite.py (patrón de conexión y PRAGMAs)_
  - _Requirements: 12.1, 12.2, 12.3, 1.2_

- [x] 15. Añadir persistencia de runs a ProjectStore en ui/project_store.py
  - File: src/agente_ong/ui/project_store.py (continúa de la tarea 14)
  - `save_run`, `update_run_status(id, status, report?, error?)`, `list_runs(project_id)`,
    guardando `report_json` vía report_serde y `params_json`
  - Purpose: asociar investigaciones a proyectos y recuperarlas (R12.5/R12.6, R6.2)
  - _Leverage: src/agente_ong/ui/report_serde.py_
  - _Requirements: 12.5, 12.6, 6.2_

- [x] 16. Test de ProjectStore en tests/ui/test_project_store.py
  - File: tests/ui/test_project_store.py
  - CRUD de proyectos, `UNIQUE(name)`, ON DELETE CASCADE de runs, round-trip de `report_json`
  - Purpose: blindar el store de proyectos/runs
  - _Leverage: tmp_path, src/agente_ong/ui/report_serde.py_
  - _Requirements: 12.2, 12.5_

- [x] 17. Implementar request_builder en ui/request_builder.py
  - File: src/agente_ong/ui/request_builder.py
  - `DEPTH_PRESETS = {"rápida": (..), "normal": (..), "exhaustiva": (..)}` (max_depth, max_pages);
    `build(base_config, *, terms, scope, depth_level, min_year, enabled_sources, direct_urls,
    search_context) -> (ResearchConfig, ResearchRequest)`; "normal" por defecto
  - Purpose: traducir controles de UI a config+request (R8/R9/R10)
  - _Leverage: src/agente_ong/research/models.py, src/agente_ong/research/config.py_
  - _Requirements: 8.1, 8.2, 8.3, 9.2, 10.1_

- [x] 18. Test de request_builder en tests/ui/test_request_builder.py
  - File: tests/ui/test_request_builder.py
  - Presets → (max_depth, max_pages); default "normal"; propagación de min_year (a config),
    enabled_sources/direct_urls (a request)
  - Purpose: garantizar el mapeo correcto de controles
  - _Leverage: src/agente_ong/ui/request_builder.py_
  - _Requirements: 8.2, 8.3, 9.2, 10.1_

- [x] 19. Implementar sort/filter de convocatorias en ui/report_view.py
  - File: src/agente_ong/ui/report_view.py
  - Funciones puras: `sort_opportunities` (orden VERIFIED → OFFICIAL_UNCROSSED →
    UNCROSSED_UNVERIFIED → CONFLICTING → NOT_FOUND) y `filter_opportunities(*, status?, min_year?,
    min_amount?)` con manejo explícito de `Claim.value is None`
  - Purpose: orden por fiabilidad y filtros (R11), sin dependencia de Streamlit
  - _Leverage: src/agente_ong/research/models.py (VerificationStatus, GrantOpportunity)_
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 20. Test de orden y filtros en tests/ui/test_report_view.py
  - File: tests/ui/test_report_view.py
  - Orden canónico de estados; filtro por estado/año/importe; combinación AND mantiene el orden;
    convocatorias con valor None no se cuelan como cero
  - Purpose: blindar la lógica de presentación de resultados
  - _Leverage: src/agente_ong/ui/report_view.py_
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 21. Implementar project_dir y validación de subida en ui/uploads.py
  - File: src/agente_ong/ui/uploads.py
  - `ALLOWED_EXT = {pdf, docx, txt, jpg, png}`, `MAX_UPLOAD_BYTES = 10*1024*1024`; `project_dir(name)`
    normaliza con `resolve()` y verifica que queda dentro de `RECURSOS/`; validadores de extensión y
    tamaño que rechazan con error claro
  - Purpose: subida segura (sin path traversal) con whitelist y límite de 10 MB (R3.2/R3.3)
  - _Leverage: .claude/steering/structure.md (convención RECURSOS/)_
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 22. Implementar save_upload, list y delete en ui/uploads.py
  - File: src/agente_ong/ui/uploads.py (continúa de la tarea 21)
  - `save_upload(name, filename, data)` con renombrado automático ante colisión (`nombre (2).ext`);
    `list_documents(name)`, `delete_document(name, filename)`
  - Purpose: gestionar los documentos del proyecto en `RECURSOS/[nombre_proyecto]/` (R3.1/R3.4/R3.5)
  - _Leverage: src/agente_ong/ui/uploads.py (project_dir/validación de la tarea 21)_
  - _Requirements: 3.1, 3.4, 3.5_

- [x] 23. Test de uploads en tests/ui/test_uploads.py
  - File: tests/ui/test_uploads.py
  - Rechazo de path traversal (`../`, ruta absoluta), extensión no permitida, tamaño > 10 MB;
    colisión → `nombre (2).ext`; escritura dentro de `RECURSOS/[proyecto]/`
  - Purpose: blindar seguridad y política de subida
  - _Leverage: tmp_path_
  - _Requirements: 3.2, 3.3, 3.5_

- [x] 24. Implementar JobManager (submit/status) en ui/jobs.py
  - File: src/agente_ong/ui/jobs.py
  - `ThreadPoolExecutor` + `threading.Lock`; `submit(project_id, config, request) -> job_id` que en
    un hilo de fondo abre su PROPIO `Investigador` (conexión SQLite propia) y ejecuta `run()`;
    `status(job_id)`, `active_jobs()`. NO llamar a `st.*` desde el hilo
  - Purpose: ejecutar investigaciones en segundo plano sin bloquear la UI (R2.1/R2.5)
  - _Leverage: src/agente_ong/research/investigador.py (Investigador.run, context manager)_
  - _Requirements: 2.1, 2.4, 2.5_

- [x] 25. Persistir el run al terminar en ui/jobs.py
  - File: src/agente_ong/ui/jobs.py (continúa de la tarea 24)
  - Al completar el Future: serializar el `ResearchReport` y `save_run`/`update_run_status` como
    `done`; capturar excepción → `error` (sin tumbar otros jobs); `pop_finished()`
  - Purpose: persistir resultados y aislar fallos (R2.3/R2.4)
  - _Leverage: src/agente_ong/ui/project_store.py, src/agente_ong/ui/report_serde.py_
  - _Requirements: 2.3, 2.4_

- [x] 26. Test de JobManager en tests/ui/test_jobs.py
  - File: tests/ui/test_jobs.py
  - Con un Investigador fake inyectable: submit → estado `done` persistido; run que lanza excepción
    → `error` persistido y otros jobs intactos
  - Purpose: garantizar ciclo de vida y aislamiento de los jobs
  - _Leverage: tmp_path, src/agente_ong/ui/project_store.py_
  - _Requirements: 2.1, 2.3, 2.4_

- [x] 27. Implementar render_report en ui/report_view.py
  - File: src/agente_ong/ui/report_view.py (continúa de la tarea 19)
  - Capa Streamlit fina: badges de estado de verificación, lista ordenada/filtrable, `unresolved`,
    `failed_sources` (R4.4) y botón de descarga (Markdown vía report_serde)
  - Purpose: presentar el informe con trazabilidad y descarga (R4/R7)
  - _Leverage: src/agente_ong/ui/report_serde.py (report_to_markdown), sort/filter de la tarea 19_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 7.1_

- [x] 28. Crear app.py con sidebar de proyectos en ui/app.py
  - File: src/agente_ong/ui/app.py
  - `main()`; sidebar con lista de proyectos (`ProjectStore`) y formulario de creación (nombre,
    objetivo, términos); al crear, valida nombre y crea `RECURSOS/[nombre]/` vía `uploads.project_dir`
  - Purpose: navegación y alta de proyectos (R1/R12.3/R12.4)
  - _Leverage: src/agente_ong/ui/project_store.py, src/agente_ong/ui/uploads.py_
  - _Requirements: 1.1, 1.2, 1.4, 12.3, 12.4_

- [x] 29. Añadir la vista de investigación con autorefresh en app.py
  - File: src/agente_ong/ui/app.py (continúa de la tarea 28)
  - Controles: términos, nivel (R8), selector de fuentes y URLs directas (R9), año mínimo (R10);
    lanzar con `request_builder` + `JobManager` (cacheado con `st.cache_resource`); `st_autorefresh`
    mientras haya jobs activos; mostrar estado en progreso/terminado y renderizar el informe
  - Purpose: lanzar investigación asíncrona y mostrar progreso/resultado (R2/R5/R8/R9/R10/R11)
  - _Leverage: src/agente_ong/ui/request_builder.py, jobs.py, report_view.py, streamlit_autorefresh_
  - _Requirements: 2.1, 2.2, 2.3, 5.1, 5.2, 8.1, 9.1, 9.2, 10.1, 11.1_

- [x] 30. Añadir el panel de documentos del proyecto en app.py
  - File: src/agente_ong/ui/app.py (continúa de la tarea 29)
  - `st.file_uploader` + guardar con `uploads.save_upload`; listar y borrar documentos del proyecto;
    mostrar errores de validación (tipo/tamaño) de forma clara
  - Purpose: subir/gestionar documentos de contexto de la ONG (R3.1/R3.4)
  - _Leverage: src/agente_ong/ui/uploads.py_
  - _Requirements: 3.1, 3.4_

- [x] 31. Declarar dependencias de UI en requirements.txt
  - File: requirements.txt
  - Añadir `streamlit` y `streamlit-autorefresh` (sondeo de estado de jobs)
  - Purpose: fijar las dependencias de la capa de UI (R2.2)
  - _Leverage: requirements.txt_
  - _Requirements: 2.2_

- [ ] 32. Smoke E2E con AppTest en tests/ui/test_app_smoke.py
  - File: tests/ui/test_app_smoke.py
  - `streamlit.testing.v1.AppTest`: crear proyecto y verlo en la lista; lanzar investigación con
    fuentes fake inyectadas y comprobar que se renderiza el informe ordenado
  - Purpose: validar el cableado extremo a extremo de la UI
  - _Leverage: streamlit.testing.v1.AppTest, tests/research/fakes.py_
  - _Requirements: 1.1, 2.1, 4.1, 11.1_
