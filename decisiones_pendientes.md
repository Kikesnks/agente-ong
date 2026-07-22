# DECISIONES_PENDIENTES — agente-ong

*Actualizado: 16-07-2026 (cierre del bloque de verificación #13/#14/#17)*

---

## #1 — [RESUELTA] Arquitectura v2: orquestación HttpReaderSource/Firecrawl
- **Decisión:** Primario HttpReaderSource, fallback Firecrawl, gating por `result_type` (R23)
- **Estado:** Implementada y validada en T17/T18

## #2 — [RESUELTA] UI: `opportunity_numbers` visibles
- **Decisión:** Numeración visible en UI y Markdown (R14)
- **Estado:** Implementada y aprobada en prueba humana UI-34 (8/8)

## #3 — [RESUELTA] UI: URL con fecha de verificación
- **Decisión:** `url_verification_suffix` incluido en URL pública (R15)
- **Estado:** Implementada y aprobada en prueba humana UI-35 (8/8)

## #7 — PENDIENTE: Cobertura de tests del modo "training"
- **Descripción:** Al blindar R23.3 (01-07-2026) se detectó que el modo "training" apenas
  tiene tests: la palabra "training" no aparecía en test_graph_flow.py antes de esta
  sesión. El modo tiene ramas propias sin ejercitar (verify() con TrainingCollector,
  opportunities queda vacío por diseño). Convendría reforzar su cobertura.
- **Impacto:** Menor, no bloquea. Deuda de test, no bug conocido.
- **Acción requerida:** Valorar un bloque de tests de "training" cuando se retome el
  investigador (¿SPEC futura o backlog?).

## #9 — PENDIENTE: Consistencia de fin de línea LF/CRLF
- **Descripción:** Git avisa "LF will be replaced by CRLF" al tocar archivos en Windows. No
  rompe nada, pero puede ensuciar diffs y crear ruido entre el Windows local y el Linux de
  Streamlit Cloud.
- **Impacto:** No bloquea. Prioridad: baja.
- **Acción requerida:** Crear `.gitattributes` con `* text=auto eol=lf`. Engancharla a
  cualquier próxima sesión que ya toque config del repo.

## #10 — PENDIENTE: `with_retry` duplicado/compartido entre `llm/` y `research/`
- **Descripción:** En T2, `llm/errors.py` importa `with_retry` desde
  `research/sources/base.py` (Opción A: no duplicar la lógica de backoff, no tocar el
  investigador). Esto crea una dependencia `llm/` -> `research/` no ideal (`llm/` es
  infraestructura reutilizable; `research/` es dominio).
- **Impacto:** No bloquea. Prioridad: media.
- **Acción requerida:** Extraer `with_retry` a un módulo neutro compartido (p.ej.
  `common/retry.py`) que usen ambos, con re-export en `research/sources/base.py` para no
  romper imports/tests existentes. Hacerlo en un refactor transversal, no dentro de una
  tarea de ejecución.

## #11 — PARCIALMENTE RESUELTA (21-07-2026): T4a (OpenAI-compatible) ejecutada; T4b (Claude) y T5 siguen pendientes
- **Descripción original:** T4 (adaptadores Claude y OpenAI de pago) y T5 (LLMConfig +
  build_provider) de `.claude/specs/integracion-llm/tasks.md` quedaban pendientes de
  ejecutar por dependencia externa: no había claves API de pago disponibles. El puerto
  `LLMProvider`, los errores propios, el adaptador Ollama (gratuito/local) y el filtro
  semántico ya funcionan y están en producción; T4/T5 solo añaden proveedores alternativos.
- **Actualización (21-07-2026):** T4 se dividió en 4a/4b al reabrirse. **4a hecha**:
  `OpenAICompatibleProvider` (`llm/adapters/openai_compatible.py`), adaptador genérico
  con `base_url`/`api_key`/`model` inyectables — sirve para OpenAI y para DeepSeek
  (verificado contra la documentación oficial de DeepSeek: API compatible con formato
  OpenAI). Tests con mocks, sin llamada real (sigue sin haber `DEEPSEEK_API_KEY`).
  **4b (Claude) y T5 (`LLMConfig`/`build_provider`) siguen pendientes**, mismo motivo de
  siempre: sin clave Anthropic, y T5 (selección de proveedor por entorno) aplaza hasta
  que haya más de un adaptador en uso real.
- **Impacto:** No bloquea. Ollama cubre el caso de uso actual (filtro semántico local,
  ~0.4s/clasificación). SPEC 3+ podrá seguir sin T4b/T5 mientras la infraestructura de
  Ollama sea suficiente. `OpenAICompatibleProvider` queda listo para usarse en cuanto
  haya clave, sin bloquear nada mientras tanto.
- **Acción requerida:**
  - Al disponer de `DEEPSEEK_API_KEY` (u otra clave OpenAI-compatible): verificar EN
    VIVO el formato de `usage_metadata`/excepciones de `OpenAICompatibleProvider` antes
    de confiar en él en producción (la traducción de excepciones hoy se basa en la
    jerarquía documentada de `openai-python`, no en una respuesta real) — mismo
    protocolo que R17.3/R19.1/R23.6 del investigador.
  - Al disponer de `ANTHROPIC_API_KEY`: ejecutar T4b siguiendo `tasks.md`, mismo
    principio de verificación en vivo antes de fijar el parseo de `langchain-anthropic`.
  - T5 sigue aplazada hasta que exista más de un proveedor de pago en uso real.

## #12 — R24.5: edición del vocabulario ODS por usuario final
- **Fecha:** 05-07-2026.
- **Estado:** aplazado a spec futura (candidato SPEC 5 o SPEC 6).
- **Contexto:** en la reapertura de investigador-v2 del 05-07-2026 se decidió
  mantener el archivo `ods_vocabulary.yaml` editable solo por el desarrollador,
  con cambios versionados en Git.
- **Motivo del aplazamiento:** requiere UI de edición, validación del contenido,
  persistencia real en Streamlit Cloud (sistema de archivos efímero) y decisión
  sobre multi-usuario. Además, primero hay que verificar con la prueba humana
  que el vocabulario ODS fijo trae resultados de calidad; sin esa base no se
  sabe qué necesita editar el usuario.
- **Referencia:** `requirements.md` de investigador-v2, sección "Fuera de
  alcance de la reapertura 05-07-2026" → R24.5.

## #13 — [CERRADA 16-07-2026] Desaparición de Tavily con R24 activo

**Fecha:** 05-07-2026.
**Estado:** cerrada.
**Contexto:** prueba humana del 05-07-2026 con búsqueda "El Salvador,
soberanía alimentaria, cooperación internacional, hispanoamérica". El
informe previo (02-07-2026, antes de R24) tenía 18/27 resultados de Tavily
y 9/27 de BDNS. El informe posterior (05-07-2026, con R24) tiene 0/60 de
Tavily y 60/60 de BDNS.
**Hipótesis a validar:** las 5 queries ODS adicionales están saturando el
pool total de hits antes de que Tavily aporte, o BDNS domina el orden de
inserción. Pérdida colateral: gems como "Ministerio de Derechos Sociales,
Consumo y Agenda 2030" (dsca.gob.es), que aparecía en el informe previo
como resultado Tavily #11, ya no aparece.
**Referencia:** informes 02-07-2026 y 05-07-2026 comparados en chat de
Claude.ai.
**Cierre (16-07-2026):** causa raíz eliminada por R25. `_derive_queries`
(graph.py:111-152) ya no genera las 5 queries fijas de R24; si
`selected_ods` está vacío se lanza `ValueError` explícito con el texto
"sin fallback al vocabulario fijo de R24". Los 5 términos fijos ya no
aparecen en ningún módulo de producción (verificado por grep en el
reconocimiento de esta sesión). La causa que produjo el 0/60 de Tavily el
05-07-2026 no existe. Prueba empírica no requerida: el mecanismo
problemático ya no está en el pipeline.
**Matiz apuntado, no reabre esta decisión:** no hay cap conjunto sobre
BDNS+Tavily; el único límite indirecto es `DEFAULT_MAX_QUERIES=30`
(config.py:20). Con muchas ODS seleccionadas podría reaparecer presión
sobre el pool por otra vía. Si se materializa, se abrirá una decisión
nueva, no se reabre #13.

## #14 — [CERRADA 16-07-2026] Falso positivo Canarias por choque de vocabulario

**Fecha:** 05-07-2026.
**Estado:** cerrada.
**Contexto:** en la misma prueba humana, 20 de 60 resultados (posiciones
21-40) son convocatorias agrícolas de la Consejería del Gobierno de
Canarias llamada "Agricultura, Ganadería, Pesca y Soberanía Alimentaria".
El término "soberanía alimentaria" del `query_terms` del usuario coincide
literalmente con el nombre de la consejería, y BDNS devuelve todas sus
convocatorias (tomate, papas, plátano, vacuno, cochinilla) que no tienen
relación con cooperación internacional ni con El Salvador.
**Causa raíz:** el problema es del cruce query_terms del usuario con
nombres de organismos en BDNS, no del vocabulario ODS de R24. R24 amplifica
el efecto al añadir más queries.
**Solución esperada:** filtro semántico de SPEC 2 (LLM que descarte hits
cuya única relación con el proyecto sea coincidencia en el nombre del
organismo).
**Cierre (16-07-2026):** infraestructura de solución en producción. Filtro
semántico enchufado incondicionalmente en el pipeline (`jobs.py:182-183` →
`enrichment.py::enrich_report` → `filter_report.py::classify_report`), con
degradación silenciosa si Ollama no está disponible. Los descartes se
exponen en la sección DESCARTADOS de las tres vistas (Markdown resumen,
Markdown detallado, render_report en Streamlit). Cobertura E2E en
`tests/ui/test_descartados_e2e.py` con los 4 orígenes de descarte
verificados. Si el falso positivo Canarias vuelve a aparecer, ahora se
descarta y se muestra al usuario etiquetado. Prueba empírica no requerida
para el cierre.

## #15 — Validación positiva de R24 (bloque D)

**Fecha:** 05-07-2026.
**Estado:** cerrado favorablemente.
**Contexto:** la misma prueba humana muestra 20 convocatorias nuevas
(posiciones 41-60) de cooperación internacional española (Barcelona,
Albacete, Pamplona, León, Girona, AECID acciones humanitarias 2026, ONG
cooperación internacional en varios ayuntamientos) que en el informe previo
del 02-07-2026 no aparecían. Es exactamente el tipo de resultado que R24
buscaba captar.
**Consecuencia:** R24 se considera efectivo. La reapertura cierra con
balance neto positivo pese a los efectos secundarios documentados en las
entradas anteriores.

---

## #16 — [CERRADA 20-07-2026] Persistencia de ODS en modelo Opportunity (`ods_principal`, `ods_secundarios`)

**Fecha:** 08-07-2026.
**Estado:** cerrada.
**Descripción:** guardar los ODS asociados a cada `Opportunity` como campos
del modelo requiere una decisión de diseño previa.
**Decisión de diseño pendiente:** ¿un ODS principal + lista de ODS
secundarios, o una lista plana de ODS sin jerarquía?
**Impacto:** bloquea a SPEC 4 (redactor con Marco Lógico) si SPEC 4 necesita
los ODS de cada convocatoria.
**Acción requerida:** decidir el diseño de los campos antes de abordar SPEC 4,
o al retomar R25.4 (ver `requirements.md` de investigador-v2, sección "Fuera
de alcance").
**Diseño acordado (16-07-2026):** `ods: list[int]` (lista plana, números
1-17). La distinción principal/secundario vive en el modelo de la
propuesta (SPEC 4), no aquí. Rellenado por LLM durante enrichment.
Vocabulario: catálogo cerrado (ya existe en `ods_catalogo.py`). Pendiente
escribir spec formal que agrupe esta decisión con #27. Contexto completo
en `Contexto_para_mi/notas_spec4.md`.
**Cierre (20-07-2026):** implementado y en producción vía la spec
`alineacion-estrategica` (tareas 1-7 de `tasks.md`). El campo `ods:
list[int]` (diseño acordado el 16-07-2026, sin distinción
principal/secundario) vive en `AlineacionEstrategica`
(`research/alignment.py`), NO en un modelo `Opportunity`: ese modelo nunca
llegó a existir en el proyecto real, algo que se descubrió y corrigió
durante la tarea 3 de la spec (commit `bde5de4`). Se rellena por LLM local
durante enrichment (`llm/alignment_extractor.py::extraer_alineacion`,
tarea 6), validado contra el rango 1-17 por
`research/alignment_parser.py::parsear_alineacion` (tarea 4), y se adjunta
a cada convocatoria vía `EnrichedReport.strategic_alignment`
(`llm/enrichment.py`, tarea 7; clave = URL normalizada), sin tocar
`research/models.py`/`GrantOpportunity`. Cobertura de tests en las 4 capas
(modelo, catálogos, parser, integración de pipeline), suite en 420 tests.
**Pendiente, no bloquea este cierre:** calibración manual del prompt de
extracción contra convocatorias reales (tarea 8 de la spec) — es un
refinamiento de calidad del prompt, no del diseño de datos que resolvía
esta decisión.

## #17 — [CERRADA 16-07-2026] Limpieza post-R25 del vocabulario ODS de R24

**Fecha:** 08-07-2026.
**Estado:** cerrada.
**Descripción:** si tras validar R25 en producción se confirma que el
fallback defensivo (`ods_vocabulary.yaml`, `ods_vocabulary.py`, tests) nunca
se activa, evaluar su eliminación.
**Principio:** código y documentación deben estar limpios; no mantener lo
innecesario.
**Momento de revisión:** tras la prueba humana post-R25 y al menos 2 semanas
de uso real.
**Cierre (16-07-2026):** eliminados `ods_vocabulary.py`, `ods_vocabulary.yaml`
y `test_ods_vocabulary.py`. El reconocimiento previo confirmó cero imports en
producción y cero cargas del YAML fuera de su propio test. Actualizados los
comentarios comparativos de `ods_catalogo.py` y `test_ods_catalogo.py` para
eliminar la referencia al módulo borrado, preservando la afirmación sobre la
ausencia de fallback. Suite tras la eliminación: 364 passed (368 − 4).
Commit: `39932ea`.

## #18 — [RESUELTA 08-07-2026] Eliminar default `selected_ods=None` en `Investigador.run()` al cerrar T26

**Fecha:** 08-07-2026.
**Estado:** resuelta.
**Descripción original:** eliminar default `selected_ods=None` en
`Investigador.run()` al cerrar T26 (multiselección obligatoria en UI).
**Motivo:** el default se puso como puente mientras la UI no propaga ODS. Al
existir UI real con multiselección obligatoria, el default deja de tener
sentido y debe convertirse en parámetro obligatorio para reforzar B1 en toda
la cadena.
**Cierre (08-07-2026):** T26 implementada (multiselect obligatorio en
`app.py`, fuera de `st.form` para que `disabled=` reaccione en vivo). Quitado
el default `=None` en `Investigador.run()` y en `Protocol._RunsInvestigation`
(`jobs.py`); `selected_ods` es ahora obligatorio en toda la cadena
`app.py → JobManager.submit → _run_job → _run_job_inner → investigador.run`.
B1 queda reforzada de punta a punta, sin ningún default transitorio.

## #19 — HttpReaderSource falla al leer URLs de BDNS y PDFs de cooperación

**Fecha:** 09-07-2026.
**Estado:** abierto.
**Descripción:** en la prueba del 09-07-2026, la sección "Fuentes con problemas" del
informe muestra 30+ URLs de subvenciones.gob.es que el lector interno no puede extraer,
más varios PDFs de aecid.es, cooperacionespanola.es y arandadeduero.es.
**Impacto:** las convocatorias BDNS aparecen solo con datos de superficie (título,
importe, plazo del listado), sin poder profundizar en detalles como criterios de
baremo, requisitos, ODS mencionados. Prioridad: media. No bloquea R25 ni al filtro
semántico.
**Acción requerida:** investigar en sesión aparte: (a) qué mecanismo de anti-bot o
headers específicos usa BDNS, (b) si es un problema de encoding/parser con los PDFs,
(c) si conviene enchufar Firecrawl como fallback más agresivamente para estos casos.
Posible candidato a spec propia si el diagnóstico revela cambios de calado.

## #20 — ENGRAM mem_doctor status: blocked — sin acción por ahora

**Fecha:** 09-07-2026.
**Estado:** documentado, sin acción.
**Descripción:** causa técnica confirmada 09-07-2026: "repair materialize-mutations"
requiere PostgreSQL local en puerto 5433 (engram_cloud) que no está montado, porque
nunca se configuró ENGRAM en modo cloud. La memoria local (SQLite) funciona
correctamente; session_summary y mem_context operan sin problema.
**Impacto:** el bloqueo es cosmético mientras no se necesite replicación cloud o
colaboración multi-máquina.
**Acción requerida:** retomar solo si: (a) se decide colaborar con otro desarrollador
en el proyecto, (b) se necesita backup/replicación de la memoria, o (c) la
actualización a versiones futuras de ENGRAM lo exige. En ese caso: instalar
PostgreSQL local, crear DB engram_cloud usuario engram puerto 5433, luego
`engram cloud repair materialize-mutations --project agente-ong --apply` seguido de
`engram cloud upgrade bootstrap`.

## #21 — Declarar `ollama` como dependencia directa en requirements.txt

**Fecha:** 09-07-2026.
**Estado:** abierto.
**Prioridad:** baja.
**Motivo:** hoy `ollama` llega transitivamente vía `langchain-ollama` y se usa en
`src/agente_ong/llm/adapters/ollama.py` (`import ollama` para tipos de excepción). Mismo
patrón de riesgo que motivó el arreglo de `python-dotenv` en commit `60c820b` (bug `.env`
del 08-09/07/2026).
**Condición de retomada:** cerrar cuando toque otra tarea del módulo `llm/adapters/` (p.ej.
reactivación de T4 con claves de Claude/OpenAI).

## #22 — Iterar el prompt de semantic_filter.md para reducir falsos negativos

**Fecha:** 09-07-2026.
**Estado:** CERRADA.
**Prioridad:** media.
**Evidencia:** T13 (09-07-2026) descartó incorrectamente BDNS 907378 ("Convocatoria de
ayudas económicas para estancias solidarias con finalidad social en el ámbito de la
cooperación internacional para el segundo semestre de 2026").
**Condición de retomada:** sesión aparte de calibración de prompt con varios ejemplos
verificados.
**Recordatorio:** "Filter problems are prompt problems" — iterar sobre
`semantic_filter.md`, no sobre código.
**Cierre (11-07-2026):** Sustituida por mini-spec `descartados-filtro`. Motivo del cambio
de estrategia: iterar el prompt para reducir falsos negativos escalaba mal (espacio de
excepciones prácticamente infinito). Se decide exponer los descartados al usuario en el
informe (sección DESCARTADOS con etiqueta de motivo) para que el humano juzgue caso por
caso. El prompt actual queda tal cual: sigue reduciendo ruido; los falsos negativos que
produzca ahora son visibles en lugar de invisibles.

## #23 — Decidir tratamiento de result_type="documento_informativo" frente al filtro semántico

**Fecha:** 09-07-2026.
**Estado:** CERRADA.
**Prioridad:** media.
**Evidencia:** T13 (09-07-2026): el filtro los descarta como "NO" (Opción 1 estricta, R6.2)
y se pierden del reporte.
**Alternativas:**
  - (A) mantener status quo.
  - (B) excluirlos del filtro (reabrir R6).
  - (C) renderizar sección "descartados" que ya persiste como parte de R7 (decisión
    pendiente ya registrada en `design.md` de `integracion-llm`).
**Condición de retomada:** antes de SPEC 4 (redactor) si va a usar documentos informativos.
**Cierre (11-07-2026):** Absorbida por mini-spec `descartados-filtro`. La sección
existente "Material informativo (no convocatorias)" se sustituye por una sección
DESCARTADOS unificada que incluye tanto los `documento_informativo` (heurística de R20)
como los descartados por el filtro semántico. Los `documento_informativo` no entran al
filtro (siempre estuvieron en su sección aparte); solo cambia el nombre y contexto de
presentación.

## #24 — [CERRADA 14-07-2026] Commitear o no scripts/verificacion_t13.py al repo

**Fecha:** 09-07-2026.
**Estado:** cerrada — postergada, sin acción inmediata.
**Prioridad:** muy baja.
**A favor:** reutilizable ante cualquier nueva investigación con filtro.
**En contra:** uso puntual, similar a los `scripts/diagnostico_tavily.py` que ya se
commitearon.
**Condición de retomada original:** decidir en el mismo commit de cierre de R7, o dejar
sin commitear en `Contexto_para_mi/`.
**Cierre (14-07-2026):** el script queda huérfano tras T3 de `descartados-filtro` (usa
`enriched.discarded`/`enriched.unclassified`, campos eliminados de `EnrichedReport`). No
se borra por ahora, ya habrá tiempo. Documentado como decisión postergada, no pendiente de
acción inmediata.

---

## Decisiones cerradas (histórico)

### #5 — [CERRADA 30-06-2026] NotFoundError en `st.expander`
- **Descripción:** `NotFoundError` aparece en ciertos contextos al usar `st.expander` en Streamlit
- **Diagnóstico:** Limitación conocida del framework Streamlit (no es bug del proyecto)
- **Decisión provisional:** No arreglar en SPEC 1; documentar como limitación conocida
- **Acción requerida:** Decidir si se aborda en SPEC 2 o se cierra definitivamente
- **Cierre (30-06-2026):** Revisado — no aparece en el código (sin captura ni manejo en
  `app.py`/`report_view.py`), sin traceback ni caso reproducible documentado, sin
  reincidencia observada desde el 28-06-2026, y no bloqueó las pruebas humanas UI-34/35.
  Se cierra como limitación conocida de Streamlit. NO entra en el alcance de SPEC 2.
- **Nota de reactivación:** Si reaparece durante las pruebas con usuarios, capturar
  navegador, pasos exactos y si había una investigación en curso con autorefresh activo —
  solo entonces se reabre con datos para investigar la hipótesis del `st_autorefresh`.

### #6 — [CERRADA 01-07-2026] `url_verification_suffix` público vs privado en spec
- **Descripción (corregida en el cierre):** la contradicción real no era una ambigüedad
  interna del spec (que era claro y consistente: `design.md` y `tasks.md` pedían la función
  `_url_verification_suffix`, con guion bajo, "privada de `report_serde.py`"), sino un
  desajuste entre el spec y el código implementado: `report_serde.py` la definió pública
  (`url_verification_suffix`, sin guion bajo) y `report_view.py` la importa desde otro
  módulo para mostrar la fecha de verificación junto a la URL (R15).
- **Impacto:** Menor — afectaba documentación y contratos de API, no funcionalidad.
- **Cierre (01-07-2026):** se ratifica el código como correcto — la función es y debe ser
  **pública**, porque `report_view.py` la necesita desde fuera de `report_serde.py`. El
  spec quedó desactualizado y se alinea con el código, no al revés. Actualizados
  `design.md:236` y `tasks.md:349` en `.claude/specs/streamlit/` para reflejar la firma sin
  guion bajo y la nota de por qué es pública.

### #4 — [CERRADA 01-07-2026] Ratificar gating R23.3
- **Descripción:** Confirmar formalmente el comportamiento de gating en el caso R23.3
- **Impacto:** No bloquea desarrollo actual
- **Acción requerida:** Revisión formal + ratificación en spec
- **Cierre (01-07-2026):** Ratificado. El gating de R23.3 (lectura profunda solo para
  convocatoria_probable) aplica SOLO en modo "calls"; en "training" se desactiva a
  propósito (el material informativo/desconocido es el objetivo del modo). El
  comportamiento existía en el código pero no en el spec: se alineó requirements.md 23.3 y
  design.md, y se blindó con el test test_read_deep_in_training_mode_fetches_all_hits
  (suite 267 en verde).

### #8 — [CERRADA 04-07-2026] `structure.md` desactualizado respecto al código real
- **Descripción:** El steering doc `.claude/steering/structure.md` proponía carpetas
  `search/` y `store/` separadas; el código real las agrupó en un módulo autocontenido
  `research/` (con `sources/` y `store/` dentro). Además `llm/` era propuesta hasta
  SPEC 2.
- **Impacto:** Documento de guía desalineado con la realidad. No bloqueaba, pero podía
  inducir a error a lectores futuros.
- **Cierre (04-07-2026):** Actualizado `structure.md` reflejando el árbol real de
  `llm/`, `research/` y `ui/`; añadida sección "reservada para specs futuras" con
  `agents/`, `graph/`, `tools/`, `export/`; corregidas referencias inexistentes a
  `agents/` y `search/` en la sección de convenciones de código; añadida en "Notas" la
  convención SDD sobre reapertura de specs para ampliaciones. Commit: `9fc3472`.

---

## #25 — [CERRADA 16-07-2026] Nombrado de archivos de informe descargable

**Fecha:** 10-07-2026.
**Estado:** cerrada.
**Prioridad:** alta.
**Evidencia:** los informes se guardaban como `informe_resumen.md` e `informe_detallado.md`
(nombre fijo, igual para cualquier proyecto/fecha). Al repetir descargas Windows genera
duplicados con sufijo numérico (evidencia empírica: `informe_detallado (2).md` e
`informe_detallado (7).md` acumulados durante la verificación T13 del 09-07-2026).
**Cierre (16-07-2026):** implementada la convención `informe_[slug-proyecto]_[fecha].md` /
`informe_detallado_[slug-proyecto]_[fecha].md` (fecha en formato `YYYY-MM-DD`, por
ordenación). Módulo nuevo `src/agente_ong/ui/filename.py` con dos funciones puras:
`slugify_project_name` (sanea el nombre del proyecto: sin tildes, minúsculas, símbolos a
`_`, tope 60 caracteres, con fallback al `project_id` si el nombre queda vacío tras sanear)
y `build_report_filename`. `render_report` (report_view.py) recibe `project_slug` y
`created_at` ya resueltos — no conoce `Project` ni aplica saneo. `app.py` resuelve ambos
justo antes de llamar a `render_report` en `_research_status`. Commit `a5a08a1`. Suite en
368 (355 previos + 13 de `test_filename.py`); se ajustaron dos llamadas dummy en
`test_report_view.py` para la nueva firma obligatoria de `render_report`.
**Hallazgo colateral:** `streamlit.testing.v1.AppTest` no expone el campo `file_name` de
`download_button` en su proto de test (solo `id, label, default, help, form_id, url,
disabled, use_container_width, type, icon, ignore_rerun, deferred_file_id, shortcut,
icon_position`) — no es posible aserción E2E sobre el nombre real del archivo descargado
vía `AppTest`; queda cubierto solo por los tests unitarios de `filename.py`.

---

## #26 — Vocabulario de cooperación española sin incorporar a las queries ODS activas

**Fecha:** 12-07-2026.
**Estado:** abierto.
**Prioridad:** media.
**Origen:** `OLD/pendientes_ods_investigador.md` (04-07-2026), ítem 1.
**Descripción:** el informe ODS del 03-07-2026 proponía 9 términos de refuerzo para las
queries, repartidos en 3 bloques: vocabulario ODS general ("Agenda 2030", "ODS"/
"Objetivos de Desarrollo Sostenible", "desarrollo sostenible cooperación"), marco español
("Plan Director cooperación española", "subvenciones 0,7%") y ejes transversales
("enfoque de género cooperación", "transición ecológica cooperación", "transición social
cooperación"). R24 (05-07-2026) implementó los 9 en `research/ods_vocabulary.yaml`. R25
(08-07-2026) sustituyó por completo el mecanismo de R24 por selección de ODS oficiales
por el usuario. Verificado en `research/graph.py::_derive_queries` (líneas 112-152) y en
`research/ods_catalogo.py`: hoy las queries ODS se generan solo a partir de
`selected_ods`, con el nombre oficial de cada uno de los 17 ODS de la ONU, sin ningún
fallback a `ods_vocabulary.yaml` (ese módulo no tiene ningún import activo fuera de sus
propios tests — código muerto, ver #17). El bloque de vocabulario ODS general quedó
cubierto por el catálogo oficial; los 5 términos del marco español y los ejes
transversales no tienen equivalente en R25 y no se generan hoy en ninguna búsqueda.
**Impacto:** medio — no bloquea nada activo, pero es pérdida real de cobertura: una
convocatoria que solo cite "Plan Director" o "subvenciones 0,7%", sin nombrar un ODS
concreto en el texto, puede no aparecer.
**Acción requerida:** decidir si estos 5 términos se reincorporan como refuerzo adicional
a las queries ODS actuales (mismo patrón de `_derive_queries`, anclado a "convocatoria")
o si se da por cerrado sin acción por considerarse cobertura suficiente. Revisar junto
con #17: si se recupera este vocabulario, #17 debería cerrarse como "no eliminar".

## #27 — [CERRADA 20-07-2026] Campos `prioridad_geografica`, `enfoques_transversales` y `plan_director_alineacion` en el modelo Opportunity

**Fecha:** 12-07-2026.
**Estado:** cerrada.
**Prioridad:** media-baja.
**Origen:** `OLD/pendientes_ods_investigador.md` (04-07-2026), ítem 2 (fuente: informe ODS
sección 6.3).
**Descripción:** además de `ods_principal`/`ods_secundarios` (ya cubiertos por la
decisión #16), el informe ODS proponía otros tres campos para el modelo `Opportunity`:
`prioridad_geografica` (lista de regiones del Plan Director — ALC, Norte de África,
Sahel; prioridad media-alta en el informe original), `enfoques_transversales` (género,
medioambiente, DDHH, diversidad cultural; prioridad media) y `plan_director_alineacion`
(transición social/ecológica/económica; prioridad baja). Ninguno de los tres está
cubierto por #16 ni existe hoy en `research/models.py`.
**Impacto:** bajo por ahora — no bloquea nada activo; podría ser relevante si SPEC 4
(redactor) necesita filtrar o priorizar convocatorias por región o eje transversal.
**Acción requerida:** decidir junto con #16 (mismo tipo de decisión de diseño: qué campos
persistir en `Opportunity` y cómo se rellenan — extracción con LLM vs metadata manual).
No urgente antes de especificar SPEC 4.
**Diseño acordado (16-07-2026):** tres listas planas —
`prioridades_geograficas`, `enfoques_transversales`,
`sectores_plan_director` (renombrado de `plan_director_alineacion` para
reflejar que contiene sectores del Plan Director). Taxonomía cerrada con
YAMLs versionados en Git, mismo patrón que `ods_catalogo`. Rellenado por
LLM durante enrichment, junto a #16. Pendiente escribir spec formal que
agrupe #16 + #27. Contexto completo en `Contexto_para_mi/notas_spec4.md`.
**Cierre (20-07-2026):** implementado junto con #16, misma spec
`alineacion-estrategica`. Los tres catálogos YAML
(`prioridades_geograficas.yaml`, `enfoques_transversales.yaml`,
`sectores_plan_director.yaml`, tarea 1) y su loader
(`research/catalogos_loader.py`, tarea 2) exponen la taxonomía cerrada del
Plan Director 2024-2027; los tres campos —renombrados exactamente como se
acordó, `prioridades_geograficas`, `enfoques_transversales`,
`sectores_plan_director`— viven en `AlineacionEstrategica` junto a `ods`
(#16), con el mismo mecanismo de extracción, validación e integración
descrito en el cierre de #16. Ningún campo vive en un modelo `Opportunity`
(nunca existió) ni se añadió a `research/models.py`. **Pendiente, no
bloquea este cierre:** la misma calibración manual del prompt (tarea 8).

## #28 — Nuevas fuentes de convocatorias: Ministerio de Derechos Sociales, ACNUDH, ONU Mujeres

**Fecha:** 12-07-2026.
**Estado:** abierto.
**Prioridad:** media-alta (alta para Ministerio de Derechos Sociales; baja para ACNUDH y
ONU Mujeres).
**Origen:** `OLD/pendientes_ods_investigador.md` (04-07-2026), ítem 3.
**Descripción:** tres fuentes oficiales candidatas a integrarse como fuente estructurada
propia (mismo patrón que `BdnsSource`/`TedSource`), no cubiertas por ninguna fuente activa
hoy: (1) Ministerio de Derechos Sociales, Consumo y Agenda 2030 — convocatoria anual de
subvenciones 0,7%, no siempre indexada en BDNS con esa etiqueta; (2) fondos temáticos de
ACNUDH (ohchr.org) — montos pequeños (15-30k USD), nicho, requiere estatus ECOSOC; (3)
fondos regionales de ONU Mujeres — específico de género, montos pequeños (hasta 20k USD).
Distinto de #13, que trata la desaparición de resultados vía Tavily, no la falta de una
fuente estructurada propia. Las fundaciones privadas y Funding & Tenders (UE), citadas en
el mismo informe origen, ya estaban identificadas aparte en
`Contexto_para_mi/implicaciones_investigacion_ongs_24-06-2026.md` y no se incluyen aquí.
**Acción requerida:** evaluar al especificar una futura versión del investigador si
conviene construir adaptadores dedicados para estas fuentes o si basta con reforzar las
queries de Tavily para captarlas mejor.

## #29 — Mostrar los 4 campos de AlineacionEstrategica en el informe detallado descargable

**Fecha:** 20-07-2026.
**Estado:** abierto.
**Prioridad:** media.
**Origen:** spec `alineacion-estrategica` (#16/#27, cerradas), sección "Impacto en UI"
de su `design.md`; confirmado con un diagnóstico en vivo de esta misma sesión.
**Descripción:** mostrar los 4 campos de `AlineacionEstrategica` (ODS, prioridades
geográficas, enfoques transversales, sectores del Plan Director) en el informe
detallado descargable (`report_to_markdown`). Fuera de alcance de la spec
`alineacion-estrategica` por diseño. Pendiente de decidir si va en spec propia o se
integra en un rediseño mayor de la UI de informes.
**Contexto técnico:** `report_to_markdown`/`report_to_markdown_summary`
(`ui/report_serde.py`) reciben un `ResearchReport`, no un `EnrichedReport` —
`strategic_alignment` vive en este último (`llm/enrichment.py`), así que hoy no hay
ni acceso al dato desde el generador del informe, aunque la extracción funcione
correctamente.
**Acción requerida:** decidir si esta spec propia debe esperar a que el redactor
(SPEC 4) necesite consumir estos campos, o si conviene resolverla antes, junto con
cualquier otro ajuste de la UI de informes.

## #30 — Enriquecer input del extractor de alineación con detalle BDNS

**Fecha:** 21-07-2026.
**Estado:** abierto.
**Prioridad:** media-alta (bloquea la tarea 8 de `alineacion-estrategica`).
**Origen:** diagnóstico en vivo durante la tarea 8 (calibración manual), aplazada
por este mismo motivo.
**Descripción:** BDNS entrega hoy al extractor de alineación estratégica solo
título + organismo + importe (200-400 caracteres, verificado con dos
convocatorias reales de run 12: 238 y 427 caracteres), sin ámbito, plazo ni
descripción. Con tan poco texto el LLM no tiene información suficiente para
determinar ODS, región prioritaria, enfoques transversales ni sector del Plan
Director, y responde vacío — comportamiento correcto dado el input, no un
fallo de prompt ni de parser. BDNS tiene un endpoint de detalle (descripción,
bases, objetivos de la convocatoria) que hoy no se está consultando antes de
pasar el texto al LLM.
**Ligada a:** decisión #19 (`HttpReaderSource` falla al leer URLs de BDNS y
PDFs), misma causa raíz de fondo — falta de contenido detallado de BDNS
disponible en el pipeline.
**Acción requerida:** evaluar consultar el endpoint de detalle de BDNS (o
mejorar la lectura en profundidad ya existente) para enriquecer el texto que
recibe `extraer_alineacion`. **Cuando se resuelva, reabrir la tarea 8** de
`alineacion-estrategica` (calibración manual del prompt) — no tiene sentido
calibrar contra un input que se sabe insuficiente.
**Nota (22-07-2026):** la investigación del 22-07-2026 refuerza la prioridad de
#30. Sin el endpoint de detalle no se pueden extraer campos que SPEC 3 y SPEC 4
necesitarán: sector CRS, marcadores CAD, cofinanciación mínima exigida, tope de
indirectos, duración máxima, exigencia de ONGD calificada, exigencia de socio
local, exigencia de línea base y evaluación externa. Referencia:
`Contexto_para_mi/informe_redaccion_proyectos_ONGs_2026-07-22.md`.

## #31 — Desincronización filtro semántico ↔ heurística documento_informativo

**Fecha:** 21-07-2026.
**Estado:** abierto.
**Prioridad:** media.
**Origen:** diagnóstico en vivo durante la tarea 8 de `alineacion-estrategica`
(caso real: convocatoria de ongdhuanca.org con `filter_verdicts="si"` y
`result_type="documento_informativo"` a la vez, run 12).
**Descripción:** un resultado puede tener veredicto `"si"` del filtro semántico
(`filter_verdicts`, gobierna si `extraer_alineaciones_del_informe` le extrae
alineación estratégica, tarea 7 de `alineacion-estrategica`) y al mismo tiempo
quedar oculto en el informe por la heurística `documento_informativo`
(`classify_for_display`, `ui/report_serde.py`, que da precedencia a esa
heurística sobre el veredicto del filtro, R3.3 de `descartados-filtro`). Son
dos juicios independientes con criterios distintos, no sincronizados entre sí.
**Impacto:** se gasta una llamada LLM de extracción de alineación en
resultados que el usuario nunca ve en el informe — coste sin beneficio visible,
no es corrupción de datos ni un fallo de cableado.
**Acción requerida:** decidir entre (a) unificar criterios (que
`classify_for_display` y el gating de extracción de alineación compartan la
misma noción de "relevante"), (b) enrutar la extracción de alineación también
por `result_type` (no extraer si `documento_informativo`, igual que ya se
excluye por veredicto `"no"`), o (c) aceptar el gasto y documentarlo como
conocido, sin cambiar código.

---

## Historial de decisiones cerradas (referencia rápida)

| # | Descripción | Fecha cierre |
|---|---|---|
| R14 | opportunity_numbers visibles en UI y Markdown | 28-06-2026 |
| R15 | URL con fecha de verificación en UI y Markdown | 28-06-2026 |
| R23 | Orquestación primario/fallback con gating result_type | ~22-06-2026 |
| UI-34 | Prueba humana opportunity_numbers | 28-06-2026 |
| UI-35 | Prueba humana URL verificación | 28-06-2026 |
| UI-36 | Color acento verde + título "Datos por confirmar" | 29-06-2026 |
| #5 | NotFoundError en `st.expander` — cerrada sin caso reproducible | 30-06-2026 |
| #6 | `url_verification_suffix` pública — spec alineado con el código | 01-07-2026 |
| #4 | Gating R23.3 ratificado (solo modo "calls") — spec alineado + test | 01-07-2026 |
| #8 | `structure.md` desactualizado — actualizado al cerrar SPEC 2 | 04-07-2026 |
| #25 | Nombrado de informes descargables `informe_[slug]_[fecha].md` | 16-07-2026 |
| #13 | Desaparición de Tavily con R24 — causa raíz eliminada por R25 | 16-07-2026 |
| #14 | Falso positivo Canarias — filtro semántico en producción con DESCARTADOS | 16-07-2026 |
| #17 | Limpieza vocabulario ODS de R24 — código muerto eliminado | 16-07-2026 |
