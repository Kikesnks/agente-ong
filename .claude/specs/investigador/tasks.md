# Implementation Plan — Agente Investigador

## Task Overview

Implementación incremental del módulo portable `src/agente_ong/research/`, de abajo a
arriba: primero modelos y configuración, luego utilidades de dominio (ledger, política de
verificación, limitador de profundidad), después la capa de fuentes y de persistencia
(puertos + adaptadores), la captura de entrenamiento, y por último la orquestación del grafo
LangGraph y la fachada pública. Cada bloque de código va acompañado de su test unitario, y
se cierra con tests de integración del flujo completo y del recall entre investigaciones.

## Steering Document Compliance

Las tareas respetan `structure.md` (paquete `research/` con subpaquetes `sources/` y
`store/`, tests espejo en `tests/research/`, descargas solo bajo `RECURSOS/ENTRENAMIENTO/`)
y `tech.md` (abstracción de fuentes, config inyectada sin secretos, LangGraph/LangChain,
ENGRAM vía puerto desacoplado).

## Atomic Task Requirements

Cada tarea toca 1-3 archivos, es completable en 15-30 min, tiene un único resultado testeable
y especifica los archivos exactos.

## Tasks

- [x] 1. Crear scaffolding del paquete research en src/agente_ong/research/__init__.py
  - File: src/agente_ong/research/__init__.py, src/agente_ong/__init__.py
  - Crear los paquetes Python vacíos con docstring de módulo; `research/__init__.py`
    declarará luego el export público de `Investigador` (placeholder por ahora)
  - Purpose: establecer la estructura importable del módulo portable
  - _Requirements: 7.1_

- [x] 2. Definir ResearchConfig en src/agente_ong/research/config.py
  - File: src/agente_ong/research/config.py
  - Dataclass `ResearchConfig` con claves de API (tavily, firecrawl, bdns, ted), ruta base de
    RECURSOS/ENTRENAMIENTO, y límites (`max_depth`, `max_pages`, `max_queries`,
    `staleness_days`); método `from_env()` que lee variables de entorno
  - Purpose: configuración inyectada sin secretos hardcodeados
  - _Requirements: 7.2, NFR Security_

- [x] 3. Definir enums y modelos base en src/agente_ong/research/models.py
  - File: src/agente_ong/research/models.py
  - Definir `VerificationStatus` (enum) y los modelos `SourceRef`, `SearchQuery`,
    `SearchHit`, `FetchedDocument` como dataclasses
  - Purpose: tipos base de procedencia y de búsqueda/lectura
  - _Requirements: 3.2, 6.1_

- [x] 4. Añadir modelos de dominio Claim y GrantOpportunity en models.py
  - File: src/agente_ong/research/models.py (continúa de la tarea 3)
  - Añadir `Claim` (con `is_critical`, `stale`, `status`, `sources`) y `GrantOpportunity`
    (campos como Claims + `overall_status`)
  - Purpose: representar datos con estado de verificación y caducidad
  - _Requirements: 1.2, 3.2, 4.4_

- [x] 5. Añadir LedgerEntry, StoredResource, ResearchRequest y ResearchReport en models.py
  - File: src/agente_ong/research/models.py (continúa de la tarea 4)
  - Añadir `LedgerEntry` (con `content_summary`, `topics`, `captured_at`), `StoredResource`,
    `ResearchRequest` (con `intent`) y `ResearchReport` (con `reused_from_ledger`,
    `unresolved`, `failed_sources`)
  - Purpose: modelos de petición, persistencia y salida del informe
  - _Requirements: 2.4, 5.1, 5.3, 7.1_

- [x] 6. Crear utilidad de normalización de URLs en src/agente_ong/research/urlnorm.py
  - File: src/agente_ong/research/urlnorm.py
  - Función `normalize_url(url) -> str` (esquema/host en minúsculas, orden de query params,
    sin fragmento) usada como clave de deduplicación
  - Purpose: deduplicar URLs equivalentes en el ledger
  - _Requirements: 5.2, 6.2_

- [x] 7. Escribir test de normalización en tests/research/test_urlnorm.py
  - File: tests/research/test_urlnorm.py
  - Casos: mayúsculas en host, fragmentos, reordenado de query params, slash final
  - Purpose: garantizar deduplicación correcta
  - _Leverage: src/agente_ong/research/urlnorm.py_
  - _Requirements: 5.2_

- [x] 8. Definir el puerto ResearchStore en src/agente_ong/research/store/base.py
  - File: src/agente_ong/research/store/base.py, src/agente_ong/research/store/__init__.py
  - Clase abstracta `ResearchStore` con métodos de ledger (`save_ledger_entry`,
    `find_ledger_by_topic`, `get_ledger_entry`) y de capturas (`has_url`, `add_resource`,
    `list_resources`)
  - Purpose: contrato de persistencia desacoplado de ENGRAM
  - _Requirements: 7.1, 7.2_

- [x] 9. Implementar InMemoryStore en src/agente_ong/research/store/memory.py
  - File: src/agente_ong/research/store/memory.py
  - Implementación en memoria de `ResearchStore`; `find_ledger_by_topic` filtra por
    coincidencia de `topics`
  - Purpose: adaptador por defecto portátil para tests y uso standalone
  - _Leverage: src/agente_ong/research/store/base.py, src/agente_ong/research/models.py_
  - _Requirements: 5.3, 7.1_

- [x] 10. Escribir test de InMemoryStore en tests/research/test_memory_store.py
  - File: tests/research/test_memory_store.py
  - Verifica guardar/recuperar `LedgerEntry`, recall por temática y `has_url`
  - Purpose: asegurar el contrato del store
  - _Leverage: src/agente_ong/research/store/memory.py_
  - _Requirements: 5.3_

- [x] 11. Implementar SourceLedger en src/agente_ong/research/ledger.py
  - File: src/agente_ong/research/ledger.py
  - Clase `SourceLedger` con vista en memoria sincronizada con `ResearchStore`:
    `mark_queried`, `seen`, `record(...content_summary, source_ref)`, `find_by_topic`,
    `entries`, `flush`; usa `normalize_url` para las claves
  - Purpose: registro persistente de fuentes con resumen y caducidad
  - _Leverage: src/agente_ong/research/store/base.py, src/agente_ong/research/urlnorm.py_
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 12. Escribir test de SourceLedger en tests/research/test_ledger.py
  - File: tests/research/test_ledger.py
  - Casos: no reprocesar URL vista, recall por temática, persistencia/rehidratación vía
    InMemoryStore, `flush`
  - Purpose: validar deduplicación y recall persistente
  - _Leverage: src/agente_ong/research/ledger.py, src/agente_ong/research/store/memory.py_
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 13. Implementar VerificationPolicy.classify en src/agente_ong/research/verification.py
  - File: src/agente_ong/research/verification.py
  - Método `classify(claim, supporting)` con las reglas: ≥2 → VERIFIED; 1 oficial →
    OFFICIAL_UNCROSSED; 1 no oficial → UNCROSSED_UNVERIFIED; 0 → NOT_FOUND; contradictorias →
    CONFLICTING
  - Purpose: estado de verificación por dato
  - _Leverage: src/agente_ong/research/models.py_
  - _Requirements: 3.3, 3.4, 4.2, 4.4_

- [x] 14. Añadir VerificationPolicy.needs_revalidation en verification.py
  - File: src/agente_ong/research/verification.py (continúa de la tarea 13)
  - `needs_revalidation(claim, intent, now)`: True si dato crítico con `intent=use_in_proposal`,
    o `captured_at` supera `staleness_days`, o procede solo de pista de ledger no reconfirmada;
    marca `stale`
  - Purpose: política de revalidación por caducidad
  - _Leverage: src/agente_ong/research/config.py, src/agente_ong/research/models.py_
  - _Requirements: 3.4, 4.1, 4.3_

- [x] 15. Escribir test de VerificationPolicy en tests/research/test_verification.py
  - File: tests/research/test_verification.py
  - Tabla de casos de `classify` (incluye OFFICIAL_UNCROSSED vs UNCROSSED_UNVERIFIED) y casos
    de `needs_revalidation` (crítico+proposal, caducidad, pista no reconfirmada)
  - Purpose: blindar las reglas de veracidad y revalidación
  - _Leverage: src/agente_ong/research/verification.py_
  - _Requirements: 3.3, 3.4, 4.2, 4.4_

- [x] 16. Implementar DepthLimiter en src/agente_ong/research/depth.py
  - File: src/agente_ong/research/depth.py, tests/research/test_depth.py
  - `DepthLimiter.can_expand(current_depth, pages_fetched)` con límites de config; test de
    corte por `max_depth`/`max_pages`/`max_queries`
  - Purpose: control de profundidad y coste
  - _Leverage: src/agente_ong/research/config.py_
  - _Requirements: 6.3, NFR Performance_

- [x] 17. Definir interfaz SearchSource en src/agente_ong/research/sources/base.py
  - File: src/agente_ong/research/sources/base.py, src/agente_ong/research/sources/__init__.py
  - Clase abstracta `SearchSource` (`name`, `is_official`, `search`, `fetch`, `supports`) y
    un helper de retry/backoff reutilizable
  - Purpose: abstracción intercambiable de proveedores
  - _Leverage: src/agente_ong/research/models.py_
  - _Requirements: 7.3, NFR Reliability_

- [x] 18. Implementar TavilySource en src/agente_ong/research/sources/tavily.py
  - File: src/agente_ong/research/sources/tavily.py
  - `search()` contra la API de Tavily (cliente HTTP inyectable), `is_official=False`,
    mapeo a `SearchHit`; clave desde config
  - Purpose: búsqueda general
  - _Leverage: src/agente_ong/research/sources/base.py, src/agente_ong/research/config.py_
  - _Requirements: 1.1, 7.2_

- [ ] 19. Implementar FirecrawlSource en src/agente_ong/research/sources/firecrawl.py
  - File: src/agente_ong/research/sources/firecrawl.py
  - `fetch(url)` contra Firecrawl devolviendo `FetchedDocument` con `content_text`,
    `raw_bytes` y `outbound_links`; `is_official=False`
  - Purpose: lectura profunda de páginas y extracción de enlaces
  - _Leverage: src/agente_ong/research/sources/base.py, src/agente_ong/research/config.py_
  - _Requirements: 2.3, 6.1_

- [ ] 20. Implementar BdnsSource en src/agente_ong/research/sources/bdns.py
  - File: src/agente_ong/research/sources/bdns.py
  - `search()` contra la API/portal BDNS (España), `is_official=True`, mapeo a `SearchHit`
    con URL oficial
  - Purpose: fuente oficial española de convocatorias
  - _Leverage: src/agente_ong/research/sources/base.py, src/agente_ong/research/config.py_
  - _Requirements: 1.1, 4.4_

- [ ] 21. Implementar TedSource en src/agente_ong/research/sources/ted.py
  - File: src/agente_ong/research/sources/ted.py
  - `search()` contra la API TED (UE), `is_official=True`, mapeo a `SearchHit` con URL oficial
  - Purpose: fuente oficial europea de convocatorias
  - _Leverage: src/agente_ong/research/sources/base.py, src/agente_ong/research/config.py_
  - _Requirements: 1.1, 4.4_

- [ ] 22. Escribir tests de fuentes con HTTP mockeado en tests/research/test_sources.py
  - File: tests/research/test_sources.py
  - Mock del cliente HTTP; verifica mapeo a `SearchHit`/`FetchedDocument`, `is_official`
    correcto, y retry/backoff ante fallo
  - Purpose: asegurar adaptadores sin red real
  - _Leverage: src/agente_ong/research/sources/tavily.py, src/agente_ong/research/sources/firecrawl.py_
  - _Requirements: 1.1, 6.1, NFR Reliability_

- [ ] 23. Implementar TrainingCollector en src/agente_ong/research/collector.py
  - File: src/agente_ong/research/collector.py
  - `collect(doc, tags)`: descarga binario o guarda texto bajo `RECURSOS/ENTRENAMIENTO/`,
    escribe sidecar de metadatos, valida ruta (anti path-traversal), salta si `store.has_url`
  - Purpose: captura de proyectos aprobados como entrenamiento
  - _Leverage: src/agente_ong/research/store/base.py, src/agente_ong/research/config.py_
  - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [ ] 24. Escribir test de TrainingCollector en tests/research/test_collector.py
  - File: tests/research/test_collector.py
  - FS temporal: descarga vs copia de texto, sidecar de metadatos, rechazo de path traversal,
    no re-descarga si URL ya capturada
  - Purpose: validar captura segura y sin duplicados
  - _Leverage: src/agente_ong/research/collector.py, src/agente_ong/research/store/memory.py_
  - _Requirements: 2.2, 2.5, NFR Security_

- [ ] 25. Definir ResearchState y nodos plan/recall_ledger en src/agente_ong/research/graph.py
  - File: src/agente_ong/research/graph.py
  - `ResearchState` (TypedDict) y nodos `plan` (deriva consultas) y `recall_ledger` (carga
    pistas vía `find_by_topic`, llena `reused_from_ledger`)
  - Purpose: arranque del grafo con recall entre investigaciones
  - _Leverage: src/agente_ong/research/ledger.py, src/agente_ong/research/models.py_
  - _Requirements: 5.3, 6.2_

- [ ] 26. Añadir nodos search/read_deep en graph.py
  - File: src/agente_ong/research/graph.py (continúa de la tarea 25)
  - `search` (consulta fuentes, registra en ledger) y `read_deep` (sigue enlaces con
    Firecrawl respetando `DepthLimiter` y el ledger)
  - Purpose: búsqueda y profundización sin repetición
  - _Leverage: src/agente_ong/research/sources/base.py, src/agente_ong/research/depth.py_
  - _Requirements: 1.1, 6.1, 6.2_

- [ ] 27. Añadir nodos verify/ask_user/compile_report y construcción del grafo en graph.py
  - File: src/agente_ong/research/graph.py (continúa de la tarea 26)
  - `verify` (aplica `VerificationPolicy` + revalidación), `ask_user` (llena `unresolved`),
    `compile_report` (arma `ResearchReport` y hace `ledger.flush`); cablear aristas y
    condición `continue?` en el grafo LangGraph
  - Purpose: cierre del ciclo de investigación
  - _Leverage: src/agente_ong/research/verification.py, src/agente_ong/research/ledger.py_
  - _Requirements: 3.1, 4.1, 4.3, 6.3_

- [ ] 28. Implementar fachada Investigador en src/agente_ong/research/investigador.py
  - File: src/agente_ong/research/investigador.py
  - Clase `Investigador` con `__init__(config, sources=None, store=None)` (defaults: fuentes
    reales + InMemoryStore) y `run(request) -> ResearchReport` que invoca el grafo
  - Purpose: contrato público portable del módulo
  - _Leverage: src/agente_ong/research/graph.py, src/agente_ong/research/config.py_
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 29. Exportar API pública en src/agente_ong/research/__init__.py
  - File: src/agente_ong/research/__init__.py (modifica de la tarea 1)
  - Exportar `Investigador`, `ResearchConfig`, `ResearchRequest`, `ResearchReport` en
    `__all__`
  - Purpose: superficie pública limpia para reutilización
  - _Leverage: src/agente_ong/research/investigador.py_
  - _Requirements: 7.1_

- [ ] 30. Implementar EngramStore en src/agente_ong/research/store/engram.py
  - File: src/agente_ong/research/store/engram.py
  - Adaptador `EngramStore(ResearchStore)` que persiste `LedgerEntry` y capturas en ENGRAM
    (cliente inyectado), con `find_ledger_by_topic` sobre la búsqueda de ENGRAM
  - Purpose: persistencia real entre sesiones sin acoplar el núcleo
  - _Leverage: src/agente_ong/research/store/base.py_
  - _Requirements: 5.3, 7.1_

- [ ] 31. Escribir test de EngramStore con ENGRAM mockeado en tests/research/test_engram_store.py
  - File: tests/research/test_engram_store.py
  - Mock del cliente ENGRAM: guarda/recupera `LedgerEntry` con `content_summary`, `topics`,
    `captured_at`; recall por temática
  - Purpose: validar el adaptador sin ENGRAM real
  - _Leverage: src/agente_ong/research/store/engram.py_
  - _Requirements: 5.3_

- [ ] 32. Crear fuentes y store fake para tests en tests/research/fakes.py
  - File: tests/research/fakes.py
  - `FakeSource` (devuelve hits/documentos fijos, configurable como oficial o no) y reutilizar
    `InMemoryStore`; helpers de fixtures
  - Purpose: dobles de prueba para integración
  - _Leverage: src/agente_ong/research/sources/base.py, src/agente_ong/research/store/memory.py_
  - _Requirements: 7.3_

- [ ] 33. Test de integración del flujo del grafo en tests/research/test_graph_flow.py
  - File: tests/research/test_graph_flow.py
  - Ejecuta `plan→recall_ledger→search→read_deep→verify→loop→compile` con fakes; verifica
    estructura del `ResearchReport`, `SourceRef` en cada dato, `failed_sources` ante fuente
    caída y `unresolved` ante not_found
  - Purpose: asegurar el ciclo completo y la trazabilidad
  - _Leverage: tests/research/fakes.py, src/agente_ong/research/investigador.py_
  - _Requirements: 1.4, 3.1, 4.4_

- [ ] 34. Test de integración de recall entre investigaciones en tests/research/test_recall.py
  - File: tests/research/test_recall.py
  - Primera `run` persiste ledger; segunda `run` reutiliza pistas (`reused_from_ledger`) y
    fuerza revalidación de datos críticos caducados (marca `stale`)
  - Purpose: validar aprendizaje persistente y revalidación
  - _Leverage: tests/research/fakes.py, src/agente_ong/research/investigador.py_
  - _Requirements: 4.1, 5.3_

- [ ] 35. Test de integración de modo training en tests/research/test_training_mode.py
  - File: tests/research/test_training_mode.py
  - `run` en modo training con FS temporal: verifica archivos bajo `RECURSOS/ENTRENAMIENTO/`,
    sidecar de metadatos e índice en store; no re-descarga en segunda ejecución
  - Purpose: validar captura end-to-end
  - _Leverage: tests/research/fakes.py, src/agente_ong/research/investigador.py_
  - _Requirements: 2.2, 2.4, 2.5_
