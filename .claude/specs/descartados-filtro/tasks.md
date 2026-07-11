# Implementation Plan — descartados-filtro

## Task Overview

Siete tareas en orden de dependencia: primero se amplía el tipo de veredicto (R2) y se le
da un lugar donde persistir (R1), luego se conecta la población real (llm/enrichment.py),
después se construye la función de presentación que decide qué mostrar (R3/R8) y se
refactorizan las 3 vistas que la consumen (Markdown resumido/detallado, Streamlit), y se
cierra con una verificación end-to-end de los 4 orígenes de descarte. Cada tarea de
código deja la suite en verde antes de pasar a la siguiente.

## Atomic Task Requirements

Cada tarea toca 1-4 archivos, tiene un resultado testeable único y especifica los
archivos y líneas exactos (según `design.md`).

## Tasks

### R2 — `ClassificationResult` ampliado

- [ ] 1. Ampliar `ClassificationResult` a 4 valores en `semantic_filter.py` y
      `filter_report.py`
  - Files: `src/agente_ong/llm/semantic_filter.py` (líneas 17, 36),
    `src/agente_ong/llm/filter_report.py` (líneas 26, 58),
    `tests/llm/test_semantic_filter.py`, `tests/llm/test_filter_report.py`
  - Cambiar el `Literal` en ambos módulos a `Literal["si", "no",
    "no_clasificado_provider", "no_clasificado_response"]`. En
    `semantic_filter.py::classify_result` (línea 36), el retorno por defecto pasa a
    `"no_clasificado_response"`. En `filter_report.py::classify_report` (línea 58,
    bloque `except LLMError`), la asignación pasa a `"no_clasificado_provider"`
  - Tests: adaptar `test_classify_result_defaults_to_no_clasificado` (renombrar a
    `..._no_clasificado_response`, `tests/llm/test_semantic_filter.py:45-58`) y las 2
    aserciones de `tests/llm/test_filter_report.py` (líneas 64 y 85) al nuevo valor
    correspondiente según el caso (respuesta sucia vs. excepción del proveedor)
  - Purpose: distinguir después del hecho por qué una oportunidad quedó sin clasificar
    (R2.1-R2.4)
  - _Leverage: los dos módulos ya definen el `Literal` de forma local y duplicada
    (patrón existente, ver design.md R1)_
  - _Requirements: R2_
  - Done: `pytest tests/llm/test_semantic_filter.py tests/llm/test_filter_report.py -q`
    en verde; ningún `"no_clasificado"` (3 valores) queda en ninguno de los dos módulos
    de producción ni en sus tests

### R1 — Persistencia de `filter_verdicts`

- [ ] 2. Añadir `filter_verdicts` a `ResearchReport` + serialización
  - Files: `src/agente_ong/research/models.py` (línea ~30, ~245),
    `src/agente_ong/ui/report_serde.py` (líneas 34-49, 106-122),
    `tests/ui/test_report_serde.py`
  - En `models.py`: nuevo `Literal` local `FilterVerdict` (mismo patrón que
    `ResultType`, sin importar nada de `llm/` — ver design.md R1); nuevo campo
    `filter_verdicts: dict[str, FilterVerdict] = field(default_factory=dict)` en
    `ResearchReport`. En `report_serde.py`: `report_to_dict` serializa
    `report.filter_verdicts` tal cual (es un dict de primitivos, sin conversión);
    `report_from_dict` lo reconstruye con `data.get("filter_verdicts", {})`
  - Tests: round-trip con `filter_verdicts` no vacío (2-3 entradas); deserialización de
    un dict SIN la clave `filter_verdicts` → `{}` sin error (retrocompat, R1.4)
  - Purpose: dar a `filter_verdicts` un hogar persistente que la UI ya sabe leer
    (`ui/app.py:320` no cambia, ver "Hallazgo clave" de design.md)
  - _Leverage: patrón retrocompatible ya usado por `result_type` en
    `opp_from_dict` (`report_serde.py:132`)_
  - _Requirements: R1_
  - Done: `pytest tests/ui/test_report_serde.py -q` en verde con los 2 tests nuevos

### R1/R2 — Población de `filter_verdicts`

- [ ] 3. Poblar `filter_verdicts` en `llm/enrichment.py::enrich_report`
  - Files: `src/agente_ong/llm/enrichment.py` (líneas 1-76),
    `src/agente_ong/llm/enrichment_serde.py`, `tests/llm/test_enrichment.py`,
    `tests/llm/test_enrichment_serde.py`
  - `EnrichedReport` pierde los campos `discarded`/`unclassified` (quedan `base` +
    `semantic_filter_applied`). `enrich_report` deja de dividir
    `report.opportunities` en 3 listas: con provider, construye
    `filter_verdicts = {normalize_url(opp.url.value or ""): classifications[id(opp)]
    for opp in report.opportunities if id(opp) in classifications}` y lo adjunta con
    `replace(report, filter_verdicts=verdicts)` — `base.opportunities` queda
    IDÉNTICA a `report.opportunities` (nada se quita). `enrichment_serde.py` se
    simplifica: `enriched_report_to_dict`/`_from_dict` ya no leen/escriben
    `discarded`/`unclassified`, solo añaden/leen `semantic_filter_applied` sobre el
    dict que produce `report_to_dict(enriched.base)` (que ya incluye
    `filter_verdicts` desde la tarea 2). `ui/jobs.py` NO se toca — sigue llamando
    `enrich_report`/`enriched_report_to_dict` igual (design.md, sección "Puntos de
    conexión")
  - Tests: reescribir `tests/llm/test_enrichment.py` (las aserciones sobre
    `.discarded`/`.unclassified` se sustituyen por aserciones sobre
    `base.opportunities == report.opportunities` sin filtrar y sobre el contenido de
    `base.filter_verdicts`); reescribir `tests/llm/test_enrichment_serde.py` (4 tests
    actuales colapsan a un round-trip de la nueva forma de `EnrichedReport` +
    verificación de que `filter_verdicts` sobrevive dentro de `base`)
  - Purpose: conectar el veredicto de cada oportunidad (T8, sin tocar) con su
    persistencia real (tarea 2), sin duplicar la información en dos estructuras
  - _Leverage: `research/urlnorm.py::normalize_url` (mismo import que ya hace
    `graph.py`), `llm/filter_report.py::classify_report` (T8, sin tocar)_
  - _Requirements: R1, R2_
  - Done: `pytest tests/llm/ -q` en verde; `scripts/verificacion_t13.py` queda
    documentado como roto por este cambio (nota en design.md, decisión #24 pendiente)
    — no se toca en esta tarea

### R3/R8 — Función clasificadora para la vista

- [ ] 4. `classify_for_display` + `partition_by_discard_status` en `report_serde.py`
  - Files: `src/agente_ong/ui/report_serde.py`, `tests/ui/test_report_serde.py`
  - Nuevas funciones puras `classify_for_display(opportunity, filter_verdicts) ->
    DisplayStatus` y `partition_by_discard_status(opportunities, filter_verdicts) ->
    tuple[list, list[tuple]]`, más el diccionario público `DISCARD_LABELS` con las 4
    etiquetas de R8 (ver design.md R3/R8 para el código exacto). Import nuevo:
    `from agente_ong.research.urlnorm import normalize_url`
  - Tests: 5 casos de `classify_for_display` (activa por `"si"`, activa por ausencia
    de veredicto, descartada_filtro, no_clasificada_provider,
    no_clasificada_response) + 1 caso de precedencia (`documento_informativo` con
    veredicto `"si"` sigue siendo `documento_informativo`, R3.3)
  - Purpose: única fuente de verdad de "qué está descartado y por qué", compartida
    por las 3 vistas (R4/R5/R6/R7)
  - _Leverage: ninguna función existente — sustituye conceptualmente a
    `partition_by_actionability` (`report_view.py:44-55`), que se elimina en la
    tarea 6_
  - _Requirements: R3, R8_
  - Done: `pytest tests/ui/test_report_serde.py -q` en verde con los 6 casos nuevos

### R4/R5/R6/R8 — Refactor de las vistas Markdown

- [ ] 5. Sustituir "Material informativo" por sección DESCARTADOS en
      `report_to_markdown`/`report_to_markdown_summary` + `opportunity_numbers`
  - Files: `src/agente_ong/ui/report_serde.py` (líneas 202-220, 223-271, 274-325),
    `tests/ui/test_report_serde.py`
  - En `report_to_markdown` (líneas 227-228, 248-255) y `report_to_markdown_summary`
    (líneas 281-282, 304-311): sustituir el cálculo de `actionable`/`informational`
    por `partition_by_discard_status` (tarea 4) y el bloque `if informational:` por
    la sección `"## Descartados (N)"` unificada (ver design.md R4/R5/R6 para el
    formato exacto de línea, con la etiqueta de R8 tras un guion). En
    `opportunity_numbers` (línea 217): sustituir la condición
    `result_type != "documento_informativo"` por
    `classify_for_display(opp, report.filter_verdicts) == "activa"`
  - Tests: sustituir en `tests/ui/test_report_serde.py` las 3 aserciones que buscan
    `"Material informativo"` (líneas 205, 253, 262) por aserciones que buscan
    `"Descartados"` y cada una de las 4 etiquetas de R8; test de "sin descartes" →
    sin sección `"Descartados"` en ninguna de las 2 vistas Markdown (R4.2/R5.2); test
    de `opportunity_numbers` con una oportunidad descartada por filtro (no solo
    `documento_informativo`) → no recibe número
  - Purpose: las 2 vistas Markdown (y sus descargas, que las reutilizan sin cambios
    de cableado) muestran DESCARTADOS con las 4 etiquetas (R4, R5, R6, R8)
  - _Leverage: `classify_for_display`/`partition_by_discard_status` (tarea 4)_
  - _Requirements: R3, R4, R5, R6, R8_
  - Done: `pytest tests/ui/test_report_serde.py -q` en verde; `grep -r "Material
    informativo" src/` sin resultados

### R7/R8 — Refactor de la UI Streamlit

- [ ] 6. Expandible DESCARTADOS colapsado con contador en `render_report`
  - Files: `src/agente_ong/ui/report_view.py` (líneas 19, 44-55, 132-134, 182-191),
    `tests/ui/test_report_view.py`
  - Eliminar `partition_by_actionability` (líneas 44-55) del módulo; sustituir su uso
    en `render_report` (líneas 132-134) por
    `partition_by_discard_status(ordered, report.filter_verdicts)` (importada de
    `report_serde.py`, ajustando el import de la línea 19). Eliminar el bloque `if
    informational: st.subheader("Material informativo...")` (líneas 182-191) y
    añadir el expandible colapsado nuevo (ver design.md R7 para el código exacto),
    colocado tras el bloque de `failed_sources` (línea 203) y antes del expander "Ver
    informe detallado" (línea 205) — cumple el orden "al final" de R7.1
  - Tests: adaptar en `tests/ui/test_report_view.py` las pruebas de
    `partition_by_actionability` (líneas 153-166, 191) a la nueva firma de 2
    argumentos de `partition_by_discard_status`; test nuevo del contador
    `"DESCARTADOS: N"` en el título del expandible; test de que el expandible no
    aparece con `N == 0` (R7.3)
  - Purpose: la vista en vivo de Streamlit muestra lo descartado sin estorbar la
    lista principal, con visibilidad inmediata del volumen (contador, R7.2)
  - _Leverage: `classify_for_display`/`partition_by_discard_status` (tarea 4),
    mismo patrón de `st.expander(..., expanded=False)` ya usado en "Filtros"
    (`report_view.py:138`) y "Detalle de los fallos" (línea 201)_
  - _Requirements: R7, R8_
  - Done: `pytest tests/ui/test_report_view.py -q` en verde; `grep -r "Material
    informativo" src/` sin resultados (confirma cierre junto con tarea 5)

### R9 — End-to-end

- [ ] 7. Verificación end-to-end de los 4 orígenes + caso sin descartes + retrocompat
      + R9.4 (coincidencia entre las 3 vistas)
  - Files: `tests/ui/test_jobs.py` (o archivo de test nuevo si se prefiere aislar el
    escenario end-to-end de los tests unitarios existentes de `jobs.py`),
    `tests/ui/test_app_smoke.py` (caso adicional R9.4, ver más abajo)
  - Un informe de prueba con 5 oportunidades (una activa, una por cada uno de los 4
    orígenes de descarte) pasado por `_run_job_inner` con un provider secuenciado
    (mismo patrón `_SequenceLLMProvider`/`_SequencedProvider` de
    `test_filter_report.py`/`test_enrichment.py`); el run persistido se relee con
    `report_from_dict` (el mismo camino de `ui/app.py:320`) y se verifica, vía
    `classify_for_display`, que las 5 oportunidades caen en el bucket esperado con
    la etiqueta correcta. Caso adicional: mismo flujo sin Ollama disponible
    (`is_ollama_available` mockeado a `False`) con un `documento_informativo` en el
    informe — debe seguir apareciendo en DESCARTADOS pese a
    `semantic_filter_applied=False` (R3.4). Caso adicional: informe sin ningún
    descarte — `partition_by_discard_status` devuelve la lista de descartados vacía

    **Caso adicional (R9.4 — coincidencia entre las 3 vistas):** sobre un mismo
    `ResearchReport` de prueba con 5 oportunidades (una activa + una por cada uno de
    los 4 orígenes de descarte), verificar que las 3 vistas coinciden en qué está
    descartado y con qué etiqueta:
    - `report_to_markdown_summary(report)`: parsear la sección `"## Descartados"` y
      extraer las 4 entradas con su etiqueta.
    - `report_to_markdown(report)`: ídem.
    - `render_report` vía `AppTest.from_function` (`streamlit.testing.v1.AppTest`,
      disponible desde Streamlit 1.28; el proyecto usa `streamlit>=1.37`) envolviendo
      directamente `lambda: render_report(report)` — **no** el patrón de
      `AppTest.from_file(app.py)` que usa T12 (`tests/ui/test_app_smoke.py`), que
      exigiría montar `JobManager`/`investigador`/proyecto completos solo para llegar
      a `render_report`. `from_function` ejercita Streamlit real (expander real,
      markdown real) con el coste de setup de un test unitario. Verificar el título
      del expandible (`"DESCARTADOS: 4"`) y su contenido.
    - Aserción: las 3 vistas producen la misma tupla `(título_oportunidad, etiqueta)`
      para cada descartada, en el mismo orden.
    - Nota de alcance: si al implementar se confirma que `AppTest.from_function`
      resulta más costoso o frágil de lo esperado, alternativa aceptable es sustituir
      el tercer punto por una verificación directa de
      `partition_by_discard_status(ordered, report.filter_verdicts)` (el mismo bucket
      que consume `render_report` sin reformatearlo), documentando en el test:
      `# R9.4 cubierto vía función clasificadora compartida; smoke test AppTest fuera
      de alcance por coste`. Decisión final al implementar T7, no ahora.
  - Tests: los 3 escenarios end-to-end descritos arriba + el caso R9.4, como tests
    nuevos
  - Purpose: cerrar la spec con evidencia de que la cadena completa
    (investigación → filtro → persistencia → relectura → presentación) funciona con
    los 4 orígenes reales, no solo con las piezas unitarias, y de que las 3 vistas del
    informe nunca se desincronizan entre sí (R9.4)
  - _Leverage: `_SequenceLLMProvider`/`_SequencedProvider` (patrón ya usado en
    `tests/llm/test_filter_report.py` y `tests/llm/test_enrichment.py`); patrón
    `AppTest` ya establecido en `tests/ui/test_app_smoke.py` (T12)_
  - _Requirements: R9, R9.4_
  - Done: `pytest -q` completo en verde (suite total, no solo los módulos tocados);
    los 3 escenarios end-to-end + el caso R9.4 pasan
