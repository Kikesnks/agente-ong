# Implementation Plan — investigador-v2

## Task Overview

Quince tareas pequeñas (una por commit) en el orden de dependencias del design: primero la
verificación sin duplicados (R14), luego el mix de fuentes (R15/R16/R17), la limpieza
(R18), la pre-clasificación (R20), el detalle BDNS (R19), las dos vistas (R22) y el cierre
manual de re-validación (R21). Cada tarea de código lleva sus tests y deja la suite en
verde.

## Atomic Task Requirements

Cada tarea toca 1-3 archivos, es completable en 15-30 min, tiene un único resultado
testeable y especifica los archivos exactos. La tarea 15 es MANUAL (conjunta con Kike).

## Tasks

### R14 — Verificación sin fuentes duplicadas

- [x] 1. dedupe_refs y conteo por URL normalizada en VerificationPolicy
  - Files: src/agente_ong/research/verification.py, tests/research/test_verification.py
  - Helper `dedupe_refs(refs)` (colapsa por `normalize_url`, conserva la ref OFICIAL ante
    duplicado, orden estable); `classify()` deduplica `supporting` antes de contar:
    VERIFIED exige 2+ URLs normalizadas DISTINTAS
  - Tests: misma URL 3 veces (no oficial) → UNCROSSED_UNVERIFIED; misma URL desde fuente
    oficial + no oficial → cuenta 1 y conserva oficialidad (OFFICIAL_UNCROSSED); dos URLs
    distintas → VERIFIED (sin cambios)
  - _Leverage: src/agente_ong/research/urlnorm.py (normalize_url)_
  - _Requirements: 14.1, 14.2, 14.4_

- [x] 2. claim.sources sin URLs repetidas en el informe (graph)
  - Files: src/agente_ong/research/graph.py, tests/research/test_graph_flow.py
  - `_classified` asigna `claim.sources = dedupe_refs(refs)`; test de regresión con el
    caso real (mismo hit/URL repetido por varias queries → nunca VERIFIED, fuentes sin
    repetidos en el informe); actualizar `test_cross_verification_statuses` a la regla
    nueva (misma URL bdns+tavily → OFFICIAL_UNCROSSED) documentando el porqué
  - _Leverage: src/agente_ong/research/verification.py (dedupe_refs, tarea 1)_
  - _Requirements: 14.2, 14.3, 14.4_

### R15 — TED fuera del modo subvenciones

- [x] 3. excluded_modes en SearchSource y exclusión en el grafo
  - Files: src/agente_ong/research/sources/base.py, src/agente_ong/research/sources/ted.py,
    src/agente_ong/research/graph.py
  - `SearchSource.excluded_modes: frozenset[ResearchMode] = frozenset()` (default
    retrocompatible); `TedSource.excluded_modes = {"calls"}` (código intacto, 15.2);
    `_active_sources` filtra por `request.mode not in source.excluded_modes`
  - _Leverage: src/agente_ong/research/graph.py (_active_sources)_
  - _Requirements: 15.1, 15.2_

- [x] 4. Tests de exclusión por modo + TED fuera de la UI
  - Files: tests/research/test_graph_flow.py, src/agente_ong/ui/app.py,
    tests/ui/test_app_smoke.py
  - Tests: en mode="calls" una fuente con excluded_modes={"calls"} no se consulta; sin
    excluded_modes todo igual. UI: quitar "ted" de `_SOURCE_LABELS` (15.3) y ajustar la
    aserción del multiselect del smoke
  - _Leverage: tests/research/fakes.py_
  - _Requirements: 15.1, 15.3_

### R16 — Vocabulario de convocatoria en Tavily

- [x] 5. call_vocabulary en config y composición de la query en TavilySource
  - Files: src/agente_ong/research/config.py, src/agente_ong/research/sources/tavily.py
  - `DEFAULT_CALL_VOCABULARY = ("convocatoria", "subvención", "ayudas", "bases
    reguladoras", "plazo de presentación")`; campo `call_vocabulary` en ResearchConfig +
    env RESEARCH_CALL_VOCABULARY (separada por comas); TavilySource compone
    `"{contexto} {términos} {vocabulario}"` (el contexto se complementa, no se sustituye)
  - _Leverage: src/agente_ong/research/config.py (_env_int, patrón from_env)_
  - _Requirements: 16.1, 16.3_

- [x] 6. Tests del vocabulario en la query
  - File: tests/research/test_sources.py
  - Con cliente fake: la query enviada contiene ≥1 término del vocabulario y conserva el
    search_context y los términos del usuario; BDNS recibe el término SIN alterar (16.2);
    vocabulario configurable por env
  - _Leverage: tests/research/test_sources.py (fakes de cliente Tavily existentes)_
  - _Requirements: 16.2, 16.4_

### R17 — Filtro temporal en Tavily

- [x] 7. min_year y published_year en TavilySource (verificar API en vivo)
  - Files: src/agente_ong/research/sources/tavily.py, src/agente_ong/research/models.py,
    src/agente_ong/research/investigador.py
  - PRIMERO: verificar EN VIVO (una llamada) si tavily-python soporta time_range/days
    (17.3); si sí, pasarlo además del filtro en cliente. `SearchHit.published_year: int |
    None = None`; TavilySource(min_year=...) cableado con config.min_year en
    _default_sources; fecha identificable = published_date del resultado o año en el
    TÍTULO; identificada y < min_year → descartar; sin fecha → conservar con
    published_year=None (17.2)
  - _Leverage: src/agente_ong/research/sources/bdns.py (patrón min_year/_too_old)_
  - _Requirements: 17.1, 17.2, 17.3_

- [x] 8. Tests del filtro temporal de Tavily
  - File: tests/research/test_sources.py
  - Casos: published_date antigua → descartado; año antiguo en el título → descartado;
    sin fecha identificable → conservado con published_year=None; min_year=None → no
    filtra; año en el cuerpo NO descarta (solo título/published_date)
  - _Leverage: tests/research/test_sources.py_
  - _Requirements: 17.1, 17.2_

### R18 — Limpieza del contenido

- [x] 9. Módulo textclean con heurísticas y límites
  - Files: src/agente_ong/research/textclean.py, tests/research/test_textclean.py
  - `clean_text(text)` (patrones de cookies/navegación/idiomas/suscripción/redes, colapso
    de espacios y líneas duplicadas) y `snippet(text, max_chars)` (truncado en palabra con
    elipsis). Tests con los ejemplos reales del diagnóstico ("Skip to content", "ES /
    CAT", aviso de cookies) y de texto útil que NO debe perderse
  - _Requirements: 18.1, 18.2_

- [x] 10. Aplicar limpieza y límites en el grafo + config
  - Files: src/agente_ong/research/config.py, src/agente_ong/research/graph.py,
    tests/research/test_graph_flow.py
  - `snippet_max_chars` (default 300) y `organism_max_chars` (default 200) en
    ResearchConfig + envs; `_build_opportunities` limpia y acota el organismo;
    `_summarize` limpia antes de truncar. Test: organismo del informe ≤ límite y sin
    texto de plantilla web
  - _Leverage: src/agente_ong/research/textclean.py (tarea 9)_
  - _Requirements: 18.1, 18.2, 18.3_

### R20 — Pre-clasificación result_type

- [x] 11. ResultType, triage heurístico y asignación en el grafo
  - Files: src/agente_ong/research/models.py, src/agente_ong/research/triage.py,
    src/agente_ong/research/graph.py
  - `ResultType` Literal + `SearchHit.result_type`/`GrantOpportunity.result_type` con
    default "desconocido" (20.3); `triage.classify_hit` según design (BDNS →
    convocatoria_probable; señales fuertes o dominio oficial → convocatoria_probable;
    Tavily sin señal fuerte → documento_informativo [16.5]; resto → desconocido);
    `_build_opportunities` asigna el mejor tipo del grupo
  - _Leverage: src/agente_ong/research/sources/ (name por fuente)_
  - _Requirements: 20.1, 20.3, 16.5_

- [x] 12. Tests de triage + serde retrocompatible + agrupación en la vista
  - Files: tests/research/test_triage.py, src/agente_ong/ui/report_serde.py,
    src/agente_ong/ui/report_view.py (+ sus tests en tests/ui/)
  - Tests de heurística por casos; serde con `data.get("result_type", "desconocido")`
    (un dict persistido ANTES de v2 carga sin error); la vista y el Markdown agrupan los
    documento_informativo aparte (20.2)
  - _Leverage: tests/ui/test_report_serde.py, tests/ui/test_report_view.py_
  - _Requirements: 20.1, 20.2, 20.3_

### R19 — Detalle BDNS (importe y plazo)

- [x] 13. Llamada al detalle en BdnsSource (verificar campos en vivo) y uso en el grafo
  - Files: src/agente_ong/research/sources/bdns.py, src/agente_ong/research/models.py,
    src/agente_ong/research/config.py, src/agente_ong/research/graph.py
  - PRIMERO: verificar EN VIVO (una llamada a `/convocatorias?numConv=...&vpd=GE`) los
    campos reales de importe y plazo. `SearchHit.amount/deadline` (None default);
    `bdns_max_detail_calls` en config (default 20, env); enriquecer tras `_to_hits` (el
    min_year YA filtró antes — 19.2) con `with_retry`, fallo de detalle no descarta el
    hit (19.4); `_build_opportunities` construye los claims de importe/plazo desde los
    campos nuevos con sus refs
  - _Leverage: src/agente_ong/research/sources/bdns.py (_FakeHttp-compatible, with_retry)_
  - _Requirements: 19.1, 19.2, 19.3, 19.4_

- [x] 14. Tests del detalle BDNS
  - Files: tests/research/test_sources.py, tests/research/test_graph_flow.py
  - Con `_FakeHttp` multi-respuesta: el detalle rellena importe/plazo; se respeta el
    límite de llamadas; NO se llama al detalle de convocatorias descartadas por min_year;
    fallo del detalle → hit sin importe/plazo pero presente; informe end-to-end con
    importe/plazo OFFICIAL_UNCROSSED y trazables
  - _Leverage: tests/research/test_sources.py (_FakeHttp), tests/research/fakes.py_
  - _Requirements: 19.1, 19.2, 19.3, 19.4_

### R22 — Dos vistas del informe

- [x] 15. Vista resumida en serde y render con dos descargas
  - Files: src/agente_ong/ui/report_serde.py, src/agente_ong/ui/report_view.py,
    tests/ui/test_report_serde.py, tests/ui/test_app_smoke.py
  - `report_to_markdown_summary` (título/organismo/importe/plazo/URL/estado, pocas líneas
    por resultado; documento_informativo aparte con título+URL); `render_report` muestra
    la resumida por defecto, toggle "Ver informe detallado", DOS botones de descarga;
    ambas vistas desde el MISMO dict persistido (22.4); ajustar smoke E2E
  - _Leverage: src/agente_ong/ui/report_serde.py (report_to_markdown), tarea 12_
  - _Requirements: 22.1, 22.2, 22.3, 22.4_

### R23 — Lectura profunda sin dependencia de créditos

- [x] 16. HttpReaderSource (httpx + trafilatura) con verificación en vivo previa
  - Files: src/agente_ong/research/sources/reader.py, requirements.txt,
    tests/research/test_sources.py
  - PRIMERO (23.6): verificación en vivo del lector contra 2-3 URLs reales del
    diagnóstico del 12-06 antes de fijar el parseo. `HttpReaderSource(SearchSource)` con
    `capabilities={"fetch"}`, name="reader": httpx (timeout, UA) + trafilatura para el
    texto principal; enlaces salientes extraídos del HTML (absolutos, dedupe, cap ~50);
    `with_retry`; extracción vacía => fallo. `trafilatura` en requirements.txt. Tests con
    fakes HTTP: documento con texto y enlaces; HTML basura => fallo; sin red
  - _Leverage: src/agente_ong/research/sources/base.py (SearchSource, with_retry),
    src/agente_ong/research/sources/firecrawl.py (mapeo a FetchedDocument)_
  - _Requirements: 23.1, 23.6_

- [x] 17. Orquestación primario/fallback, gating por result_type y límites
  - Files: src/agente_ong/research/config.py, src/agente_ong/research/graph.py,
    src/agente_ong/research/investigador.py, src/agente_ong/ui/app.py
  - `reader_max_pages` (default 15) y `firecrawl_max_calls` (default 0) en ResearchConfig
    + envs; `read_deep`: frontera solo con hits convocatoria_probable (direct_urls siempre;
    los enlaces salientes heredan elegibilidad), primario = primer fetcher, fallback con
    contador por investigación (0 = nunca); fallo de lectura no descarta el hit (23.5);
    `_default_sources` construye HttpReaderSource SIEMPRE (delante de Firecrawl); UI:
    entrada "firecrawl" de _SOURCE_LABELS pasa a "reader" ("Lectura de páginas y URLs
    directas")
  - _Leverage: src/agente_ong/research/sources/reader.py (tarea 16)_
  - _Requirements: 23.2, 23.3, 23.4, 23.5_

- [x] 18. Tests de integración del flujo de lectura v2
  - Files: tests/research/test_graph_flow.py, tests/ui/test_app_smoke.py
  - Casos: solo los convocatoria_probable consumen lectura profunda (los
    documento_informativo no); direct_urls se leen siempre; fallo del primario con
    firecrawl_max_calls=0 => sin fallback, hit conservado y fallo reflejado; con
    firecrawl_max_calls=N => fallback invocado como máximo N veces; reader_max_pages
    respetado; smoke ajustado a la fuente "reader"
  - _Leverage: tests/research/fakes.py (FakeFetchSource)_
  - _Requirements: 23.2, 23.3, 23.4, 23.5_

### R21 — Re-validación con casos reales (MANUAL, conjunta con Kike)

- [ ] 19. [MANUAL — NO autónoma] Re-ejecutar las dos búsquedas del 12-06-2026 y documentar
  - File: Contexto_para_mi/revalidacion_investigador_v2.md (documento nuevo)
  - Con Kike: mismas dos búsquedas (términos y contexto del 12-06-2026); comparar con
    NÚMEROS ABSOLUTOS además de porcentajes (total de resultados, cuántos con
    importe/plazo, cuántos tipo convocatoria): % y nº de resultados tipo convocatoria,
    importe/plazo presentes en BDNS, sin duplicados en verificación, sin licitaciones
    TED, sin documentos pre-min_year con fecha conocida (21.1); documentar antes/después
    como material de portafolio (21.2); dejar constancia de que la validación de criterio
    fino queda para testers expertos (21.3)
  - _Requirements: 21.1, 21.2, 21.3_
