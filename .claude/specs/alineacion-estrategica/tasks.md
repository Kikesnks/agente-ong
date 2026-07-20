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

## Estado al cierre de sesión (2026-07-20)

**Completadas (T1-T7, T9):** implementación funcional completa de R1-R7, suite en
420 tests (partida: 364), todos los commits en `main` (local, push manual
pendiente por el usuario). T9 se ejecutó fuera de orden (antes que T8, a petición
explícita del usuario) con alcance acotado: cerró #16/#27 en
`decisiones_pendientes.md` y marcó este `tasks.md`, pero **no tocó
`estado_proyecto.md`** (ya estaba al día desde el cierre de sesión anterior) **ni
`Contexto_para_mi/notas_spec4.md`** (sin verificar en esta tarea — ver su nota
"Estado: completada"). Detalle de cada tarea en su propia nota más abajo.

**Pendiente:**

- **Tarea 8 (calibración manual del prompt):** no empezada. Requiere Ollama local
  arrancado, un conjunto de ≥10 convocatorias reales representativas (ODS y
  regiones diversos) y revisión manual de los cuatro campos extraídos — sin tocar
  código salvo el propio `opportunity_alignment.md`. Ver el "Riesgo a vigilar" de
  la tarea 8: si tras 3-4 iteraciones no se alcanza el 80%, parar y abrir decisión
  en `decisiones_pendientes.md`, no forzar el resultado. Nota: #16/#27 ya están
  cerradas (T9) aunque T8 siga pendiente — el cierre documental consideró que la
  calibración es un refinamiento de calidad del prompt, no parte del diseño de
  datos que resolvían esas dos decisiones.

**Decisiones abiertas que afectan a T8:**

- Ninguna decisión de arquitectura queda abierta para T8 (solo trabajo de
  calibración manual, sin código nuevo salvo el `.md` del prompt).
- Si al hacer T8 se revisa `Contexto_para_mi/notas_spec4.md` y aparece "el modelo
  Opportunity" como referencia, corregirlo igual que se corrigió en `design.md`/
  `requirements.md` (commit `bde5de4`, tarea 3): ese modelo nunca existió en el
  proyecto real.

## Atomic Task Requirements

Cada tarea toca un componente único (catálogo, loader, modelo, parser, prompt, extractor,
integración, calibración o documentación), tiene un resultado testeable (salvo la
creación del prompt inicial, su calibración manual y el cierre documental, que no llevan
test automático) y especifica los archivos exactos según `design.md`.

## Tasks

### R2/R3/R4 — Catálogos YAML de alineación estratégica

- [x] 1. Crear los tres catálogos YAML (prioridades geográficas, enfoques
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
  - **Estado: completada.** Commit `a5e3de7`. Sin tests (como preveía la tarea);
    verificación manual (`yaml.safe_load` + recuento) hecha en el momento, no queda
    persistida como test hasta la tarea 2.

### R2/R3/R4 — Loader de catálogos

- [x] 2. `catalogos_loader.py` con las cuatro funciones puras
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
  - **Estado: completada.** Commit `0505a5f`. Decisión de implementación resuelta:
    híbrido (helpers internos compartidos para I/O sin-fallback, funciones públicas
    independientes por catálogo, ya que sectores tiene forma jerárquica distinta a
    prioridades/enfoques). 26 tests. `obtener_transicion_de_sector` devuelve el
    `nombre` de la transición (p.ej. "Transición social"), no el `id`.

### R1 — Modelo AlineacionEstrategica

**Corrección (2026-07-20):** no existe modelo `Opportunity` en el proyecto (ver
`design.md`, sección "Modelo de datos"). Los cuatro campos se agrupan en un contenedor
nuevo, `AlineacionEstrategica`, independiente de `GrantOpportunity`/`research/models.py`.

- [x] 3. Crear `AlineacionEstrategica` con los cuatro campos de alineación estratégica
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
  - **Estado: completada.** Commit `da04f2c`, precedido por el commit de corrección
    documental `bde5de4` (`docs(spec): corregir modelo Opportunity inexistente y
    ruta de jobs.py en alineacion-estrategica`): al abrir el código para esta tarea
    se descubrió que no existe ningún modelo `Opportunity` en el proyecto (ver la
    "Corrección (2026-07-20)" justo arriba). Consultado con el usuario: se
    confirmó explícitamente **no tocar `research/models.py`/`GrantOpportunity`**;
    `AlineacionEstrategica` vive en `research/alignment.py`, independiente. Esta
    decisión sigue vigente y condicionó también la tarea 7. 4 tests.

### R5 — Parser de la respuesta LLM

- [x] 4. `alignment_parser.py`: `parsear_alineacion` + `AlignmentParseError`
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
  - **Estado: completada.** Commit `ec73089`. 10 tests (los 6 pedidos + variantes
    por campo de catálogo). `ods` con elementos no-`int` (p.ej. strings) se
    descarta igual que fuera de rango, no cuenta como error de estructura.

### R6 — Prompt de extracción

- [x] 5. `opportunity_alignment.md` (versión inicial)
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
  - **Estado: completada.** Commit `08c895e`. Placeholders `<<ODS>>`,
    `<<PRIORIDADES_GEOGRAFICAS>>`, `<<ENFOQUES_TRANSVERSALES>>`,
    `<<SECTORES_PLAN_DIRECTOR>>` (no `{llaves}`, deliberado: el bloque de salida
    JSON del propio prompt usa llaves literales y chocaría). La tarea 6 los
    sustituye con `.replace()`, no con `str.format()`. Pendiente de calibración
    real en la tarea 8.

### R7 — Extractor LLM

- [x] 6. `alignment_extractor.py`: `extraer_alineacion`
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
  - **Estado: completada.** Commit `4741635`. Precisiones sobre la firma de
    `design.md` (no contradicen la spec): `llm_client: LLMClient` → `provider:
    LLMProvider | None` (mismo patrón que `enrich_report`, la disponibilidad de
    Ollama se resuelve en el caller, no aquí); se añadió `opportunity_id: str |
    None = None` (keyword-only), pedido por esta misma tarea para los logs pero
    ausente en la firma de `design.md`. A diferencia de `enrich_report`
    (degradación 100% silenciosa), aquí SÍ hay logs WARNING/ERROR por requisito
    explícito de R7. 7 tests (los 4 pedidos + 2 de detalle).

### R7 — Integración en el pipeline de enrichment

- [x] 7. Conectar `extraer_alineacion` en `ui/jobs.py` tras el filtro semántico
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
  - **Estado: completada, con dos correcciones sobre el texto de arriba (no
    reabrir la tarea por esto, ya implementado y verificado):**
    - **`ui/jobs.py` NO se tocó.** El punto real de integración es
      `enrich_report` (`llm/enrichment.py`), al que `ui/jobs.py` ya llamaba sin
      cambios; extender `enrich_report` bastó para que la persistencia
      (`enriched_report_to_dict` → SQLite) incluyera la alineación.
    - **No se creó `tests/research/test_jobs_alignment.py`.** Los 5 escenarios
      quedaron repartidos en: `tests/llm/test_alignment_report.py` (nuevo, 5
      tests, mirror de `test_filter_report.py`), `tests/llm/test_enrichment.py`
      (+3 tests, +3 reparados), `tests/llm/test_enrichment_serde.py` (+1 test),
      `tests/ui/test_descartados_e2e.py` (1 test reparado). `ui/jobs.py` ya
      tenía su propia cobertura en `tests/ui/test_jobs.py`, no tocada.
    - Commit `42c4cfa`. Campo nuevo `EnrichedReport.strategic_alignment: dict[url
      normalizada, AlineacionEstrategica]` (`llm/enrichment.py`), poblado en
      `enrich_report` reutilizando las mismas `classifications` que ya arma
      `filter_verdicts` (sin llamada extra de clasificación). Gating: extracción
      SOLO si el veredicto es exactamente `"si"` (no para
      `no_clasificado_provider`/`no_clasificado_response`).
    - **Decisión de diseño no cubierta por la spec, resuelta:** dónde vive
      `strategic_alignment`. Se descubrió que `filter_verdicts` SÍ vive como
      campo directo en `ResearchReport`/`research/models.py` (precedente de la
      spec `integracion-llm`, anterior a la regla acordada en la tarea 3). Se
      mantuvo la regla de la tarea 3 vigente: `strategic_alignment` vive en
      `EnrichedReport` (`llm/enrichment.py`), `research/models.py` sigue
      intacto. **Si T8/T9 o una spec futura necesitan mostrar la alineación en
      la UI, este es el campo a leer** (vía `enriched_report_from_dict`), no
      nada en `research/models.py`.

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

- [x] 9. Cerrar #16 y #27 en la documentación viva
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
  - **Estado: completada** (alcance acotado explícitamente por el usuario para esta
    ejecución: solo `decisiones_pendientes.md` + este `tasks.md`, commit
    `docs(spec): cerrar T9 y decisiones #16/#27`). #16 y #27 cerradas en
    `decisiones_pendientes.md` con referencia a las 7 tareas de esta spec y a los
    commits concretos de cada una. `estado_proyecto.md` ya quedó actualizado con la
    nueva capacidad en el cierre de sesión anterior (2026-07-20, gitignored, no
    versionado). `Contexto_para_mi/notas_spec4.md` (gitignored) **no se ha
    verificado/actualizado en esta tarea** — queda pendiente si alguien lo consulta
    y encuentra #16/#27 todavía como prerrequisito abierto.

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
