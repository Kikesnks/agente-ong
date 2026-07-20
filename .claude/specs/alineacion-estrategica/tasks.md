# Implementation Plan — alineacion-estrategica

## Task Overview

Nueve tareas en orden de dependencia: primero los tres catálogos YAML (R2/R3/R4) y su
loader, después el modelo (R1) que los consumirá, luego el parser (R5) que valida contra
esos catálogos, el prompt inicial (R6) y el extractor LLM (R7) que lo usa, la integración
en el pipeline de enrichment (R7) que conecta todo tras el filtro semántico existente, y
se cierra con la calibración manual del prompt (R6) y el cierre documental de las
decisiones #16/#27. Cada tarea de código deja la suite en verde antes de pasar a la
siguiente; cada tarea es un commit único (`feat:`/`test:` para código, `docs(spec):` para
el cierre documental, nunca mezclados).

## Atomic Task Requirements

Cada tarea toca un componente único (catálogo, loader, modelo, parser, prompt, extractor,
integración, calibración o documentación), tiene un resultado testeable (salvo la
creación del prompt inicial, su calibración manual y el cierre documental, que no llevan
test automático) y especifica los archivos exactos según `design.md`.

## Tasks

### R2/R3/R4 — Catálogos YAML de alineación estratégica

- [ ] 1. Crear los tres catálogos YAML (prioridades geográficas, enfoques
      transversales, sectores del Plan Director)
  - Files: `src/agente_ong/research/catalogos/prioridades_geograficas.yaml` (nuevo),
    `src/agente_ong/research/catalogos/enfoques_transversales.yaml` (nuevo),
    `src/agente_ong/research/catalogos/sectores_plan_director.yaml` (nuevo)
  - Contenido literal según `design.md` ("Formato de los catálogos YAML"): 4
    prioridades geográficas, 6 enfoques transversales, 13 sectores organizados en 3
    transiciones (social/ecológica/económica) con sus ODS de referencia; cada archivo
    incluye bloque `fuente:` (documento, NIPO, sección)
  - Tests: ninguno en esta tarea — la cobertura se verifica en la tarea 2 (loader)
  - Purpose: fuente de verdad versionada en Git para la taxonomía cerrada que usarán
    el parser (tarea 4) y el prompt (tarea 5)
  - _Leverage: mismo patrón de catálogo YAML versionado que
    `research/ods_catalogo.yaml` (R25 de `investigador-v2`)_
  - _Requirements: R2, R3, R4_
  - Done: los tres YAML parsean con `yaml.safe_load` sin error; sin duplicados dentro
    de cada catálogo; commit `feat: catálogos YAML de alineación estratégica (Plan
    Director 2024-2027)`

### R2/R3/R4 — Loader de catálogos

- [ ] 2. `catalogos_loader.py` con las cuatro funciones puras
  - Files: `src/agente_ong/research/catalogos_loader.py` (nuevo),
    `tests/research/test_catalogos_loader.py` (nuevo)
  - Antes de escribir código: examinar el loader de `ods_catalogo.py` existente y
    decidir entre loader único genérico vs. loaders independientes (`design.md`,
    "Decisión de implementación abierta" — decisión de implementación, no bloquea la
    tarea). Implementar `cargar_prioridades_geograficas() -> list[str]`,
    `cargar_enfoques_transversales() -> list[str]`,
    `cargar_sectores_plan_director() -> list[str]`,
    `obtener_transicion_de_sector(sector: str) -> str` (lanza `ValueError` si el
    sector no existe en el catálogo)
  - Tests: carga correcta de los 3 catálogos; recuento exacto (4, 6, 13);
    coincidencia literal con la fuente oficial; ausencia de duplicados;
    `obtener_transicion_de_sector` correcto para los 13 sectores + `ValueError` para
    un sector inventado
  - Purpose: exponer la taxonomía cerrada como funciones puras que consumirán el
    parser (tarea 4) y el prompt (tarea 5)
  - _Leverage: patrón sin-fallback de `research/ods_catalogo.py::load_ods_catalogo`
    (lanza `ValueError` explícito, sin degradar silenciosamente)_
  - _Requirements: R2, R3, R4_
  - Done: `pytest tests/research/test_catalogos_loader.py -q` en verde; commit
    `feat: loader de catálogos de alineación estratégica + tests`

### R1 — Modelo AlineacionEstrategica

**Corrección (2026-07-20):** no existe modelo `Opportunity` en el proyecto (ver
`design.md`, sección "Modelo de datos"). Los cuatro campos se agrupan en un contenedor
nuevo, `AlineacionEstrategica`, independiente de `GrantOpportunity`/`research/models.py`.

- [ ] 3. Crear `AlineacionEstrategica` con los cuatro campos de alineación estratégica
  - Files: `src/agente_ong/research/alignment.py`, `tests/research/test_alignment.py`
  - Dataclass con `ods: list[int] = field(default_factory=list)`,
    `prioridades_geograficas: list[str] = field(default_factory=list)`,
    `enfoques_transversales: list[str] = field(default_factory=list)`,
    `sectores_plan_director: list[str] = field(default_factory=list)`
  - Tests: creación sin los cuatro campos → defaults `[]`; creación con los cuatro
    poblados → se preservan íntegros; ronda serialize→deserialize preserva las
    cuatro listas, incluyendo el caso todas `[]`
  - Purpose: dar a la alineación estratégica un contenedor donde persistir el
    resultado que producirán el parser (tarea 4) y el extractor (integrado en la
    tarea 7)
  - _Leverage: patrón `default_factory=list` ya usado en los campos de lista de
    `research/models.py`_
  - _Requirements: R1_
  - Done: `pytest tests/research/test_alignment.py -q` en verde; commit
    `feat: modelo AlineacionEstrategica con los cuatro campos de alineación
    estratégica + tests`

### R5 — Parser de la respuesta LLM

- [ ] 4. `alignment_parser.py`: `parsear_alineacion` + `AlignmentParseError`
  - Files: `src/agente_ong/research/alignment_parser.py` (nuevo),
    `tests/research/test_alignment_parser.py` (nuevo)
  - `AlignmentParseError(Exception)`; usa el contenedor de retorno
    `AlineacionEstrategica` de `research/alignment.py` (tarea 3);
    `parsear_alineacion(respuesta_llm_cruda: str) -> AlineacionEstrategica`: parsea
    JSON (falla → `AlignmentParseError`),
    verifica los 4 campos y sus tipos (estructura incorrecta → `AlignmentParseError`),
    descarta por catálogo con log WARNING, valida rango 1-17 en `ods`, colapsa
    duplicados preservando orden de primera aparición
  - Tests: caso feliz; valores fuera de catálogo (mezcla válidos/inválidos); ODS
    fuera de rango (`[3, 18, 0, -1, 5]` → `[3, 5]`); duplicados; JSON malformado →
    `AlignmentParseError`; estructura incorrecta → `AlignmentParseError`
  - Purpose: frontera de validación entre la respuesta libre del LLM y la taxonomía
    cerrada (R1.4)
  - _Leverage: `catalogos_loader` (tarea 2) para las listas de valores válidos_
  - _Requirements: R5_
  - Done: `pytest tests/research/test_alignment_parser.py -q` en verde con los 6
    casos; commit `feat: parser de alineación estratégica contra catálogos + tests`

### R6 — Prompt de extracción

- [ ] 5. `opportunity_alignment.md` (versión inicial)
  - Files: `src/agente_ong/llm/prompts/opportunity_alignment.md` (nuevo)
  - Rol y tarea, placeholder de taxonomía inyectable en runtime (no hardcodeada),
    instrucciones de formato de salida (JSON plano, sin texto adicional), al menos
    un ejemplo few-shot inicial — la calibración fina se hace en la tarea 8
  - Tests: ninguno — la calidad del prompt no es objeto de test automático (R6,
    "fuera de la cobertura automática")
  - Purpose: instrucción base para el extractor (tarea 6); versión funcional de
    partida, no definitiva
  - _Leverage: mismo patrón de prompt calibrable de `llm/prompts/semantic_filter.md`_
  - _Requirements: R6_
  - Done: el archivo existe con la estructura descrita; commit `feat: prompt inicial
    de extracción de alineación estratégica`

### R7 — Extractor LLM

- [ ] 6. `alignment_extractor.py`: `extraer_alineacion`
  - Files: `src/agente_ong/llm/alignment_extractor.py` (nuevo),
    `tests/llm/test_alignment_extractor.py` (nuevo)
  - `extraer_alineacion(opportunity_text, llm_client) -> AlineacionEstrategica |
    None`: si Ollama no disponible → log WARNING + `None`; si disponible, carga la
    taxonomía (tarea 2), la inyecta en el prompt (tarea 5), llama al LLM y pasa la
    respuesta al parser (tarea 4); si la llamada falla o el parser lanza
    `AlignmentParseError` → log ERROR con `opportunity_id` si está disponible + `None`
  - Tests: Ollama disponible + respuesta válida → `AlineacionEstrategica` correcta;
    Ollama no disponible → `None` + WARNING; Ollama disponible + respuesta
    malformada → `None` + ERROR; la llamada lanza excepción → `None` + ERROR (Ollama
    mockeado en los 4 casos)
  - Purpose: implementa las reglas de degradación de R7 (ausencia de Ollama, error
    puntual) de forma aislada y testeable antes de conectarlo al pipeline (tarea 7)
  - _Leverage: patrón de degradación silenciosa ya usado por el filtro semántico
    (`llm/filter_report.py`)_
  - _Requirements: R7_
  - Done: `pytest tests/llm/test_alignment_extractor.py -q` en verde con los 4
    casos; commit `feat: extractor LLM de alineación estratégica + tests`

### R7 — Integración en el pipeline de enrichment

- [ ] 7. Conectar `extraer_alineacion` en `ui/jobs.py` tras el filtro semántico
  - Files: `src/agente_ong/ui/jobs.py` (corregido 2026-07-20: no existe
    `research/jobs.py`; el punto real de integración del enrichment es
    `ui/jobs.py`, que ya importa de `llm/` — ver `enrich_report`),
    `tests/research/test_jobs_alignment.py` (nuevo)
  - Tras el punto donde se decide si la convocatoria pasa el filtro semántico: si es
    descartada, no se llama al extractor (campos quedan `[]`); si es relevante, se
    llama a `extraer_alineacion` (tarea 6) y se pueblan los cuatro campos del
    `Opportunity` si devuelve resultado, o quedan `[]` si devuelve `None`
  - Tests: descartada por filtro → sin llamada al extractor, campos `[]`; relevante +
    extracción exitosa → campos poblados; relevante + Ollama no disponible → campos
    `[]`, pipeline continúa; relevante + error puntual → campos `[]` solo para esa
    convocatoria, las demás siguen; relevante + respuesta malformada → campos `[]` +
    log ERROR (todos con Ollama mockeado)
  - Purpose: cierra el flujo end-to-end descrito en R7 dentro del pipeline real de
    enrichment
  - _Leverage: punto de enganche existente del filtro semántico en `jobs.py` (no se
    toca su lógica, solo se añade el paso siguiente)_
  - _Requirements: R7_
  - Done: `pytest tests/research/test_jobs_alignment.py -q` en verde con los 5
    escenarios; commit `feat: integrar extracción de alineación en pipeline de
    enrichment + tests`

### R6 — Calibración manual del prompt

- [ ] 8. Calibrar `opportunity_alignment.md` contra convocatorias reales
  - Files: `src/agente_ong/llm/prompts/opportunity_alignment.md` (edición
    iterativa), opcionalmente `Contexto_para_mi/notas_calibracion_alignment.md`
    (nuevo, gitignored)
  - Conjunto de al menos 10 convocatorias reales representativas (ODS y regiones
    diversos); ejecutar el pipeline completo en local con Ollama; revisar
    manualmente los cuatro campos extraídos; iterar el prompt (instrucciones,
    ejemplos few-shot, formato) — sin tocar código
  - Tests: ninguno automático — verificación manual contra el criterio de
    aceptación de R6 y del `design.md`
  - Purpose: llevar el prompt de una versión funcional (tarea 5) a una calibrada
    empíricamente, igual que se hizo con `semantic_filter.md`
  - _Leverage: mismo proceso de calibración manual ya establecido para el filtro
    semántico_
  - _Requirements: R6_
  - Done: al menos el 80% de las convocatorias del conjunto de calibración tiene
    los cuatro campos coherentes con la anotación humana; los descartes por
    catálogo (logs WARNING) no revelan invención sistemática; commit `feat: prompt
    de alineación calibrado contra convocatorias reales`
  - Riesgo a vigilar: si tras 3-4 iteraciones no se alcanza el 80%, parar y abrir
    una decisión en `decisiones_pendientes.md` sobre si el modelo local es
    suficiente, en vez de forzar el resultado

### Cierre documental de la spec

- [ ] 9. Cerrar #16 y #27 en la documentación viva
  - Files: `decisiones_pendientes.md`, `estado_proyecto.md`,
    `Contexto_para_mi/notas_spec4.md`, este `tasks.md`
  - Marcar #16 y #27 como cerradas en `decisiones_pendientes.md` con referencia a
    esta spec y al último commit relevante; actualizar `estado_proyecto.md`
    describiendo brevemente la nueva capacidad de alineación estratégica; verificar
    que `notas_spec4.md` refleje que #16+#27 ya no son prerrequisito pendiente;
    marcar todos los checkboxes de este archivo
  - Tests: ninguno
  - Purpose: dejar constancia formal de que la fusión de #16+#27 quedó
    implementada, siguiendo el patrón de cierre ya usado en el resto de decisiones
    del proyecto
  - _Leverage: patrón de cierre "Cierre (fecha):" ya usado para #13, #14, #17_
  - _Requirements: sin requisito técnico asociado — tarea documental de cierre_
  - Done: `pytest -q` completo en verde (suite total); `git status` sin pendientes
    de código; commit `docs(spec): cerrar alineacion-estrategica (#16, #27
    implementadas)`

## Notas operativas

- Push a `main`: manual desde el terminal, nunca automático; a criterio del
  usuario (sugerencia: tras las tareas 2, 4, 7 y 9 como hitos intermedios estables).
- Commits de código con prefijo `feat:`/`test:`; el cierre documental con
  `docs(spec):`. Nunca mezclados en el mismo commit.
- Antes de cada tarea: `pytest -q` para confirmar partida en verde. Al terminar:
  `pytest -q`, `git status`, commit específico.
- Si aparece deuda técnica no relacionada durante la implementación (p. ej.
  decisión #10 pendiente): anotar en `decisiones_pendientes.md`, no atacarla dentro
  de esta spec.
- Verificación final tras la tarea 9: `pytest -q` verde, `git status` limpio,
  recuento de tests coherente con el punto de partida (364) más los nuevos de las
  tareas 2, 3, 4, 6 y 7.
