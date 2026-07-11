# Spec descartados-filtro — requirements.md

## Origen

**Motivo:** el filtro semántico de `integracion-llm` (SPEC 2, R6, Opción 1) clasifica
**todos** los resultados con una única pregunta SI/NO. La verificación empírica de T13
(09-07-2026) confirmó un falso negativo real: BDNS 907378 ("Convocatoria de ayudas
económicas para estancias solidarias...") fue descartada incorrectamente por el filtro
(ver `Contexto_para_mi/decisiones_pendientes.md` #22). La estrategia original prevista
para ese hallazgo era iterar el prompt (`semantic_filter.md`); se descarta como enfoque
principal porque el espacio de excepciones de un filtro semántico es prácticamente
infinito — perseguir cada falso negativo con más reglas de prompt escala mal.

**Cambio de estrategia (decisión de producto, 11-07-2026):** en vez de perseguir la
perfección del filtro, se expone al usuario lo que el filtro y la heurística R20
descartan, con el motivo concreto, para que el humano juzgue caso por caso. El prompt
actual (`llm/prompts/semantic_filter.md`) queda tal cual — sigue reduciendo ruido; sus
falsos negativos pasan de ser invisibles a ser visibles y revisables.

Esta spec sustituye y cierra las decisiones pendientes **#22** (iterar el prompt) y
**#23** (tratamiento de `documento_informativo` frente al filtro).

**Naturaleza de la spec:** es una spec de **presentación**, no estructural. No se crea
ningún modelo de dominio nuevo (`GrantOpportunity` no cambia su forma; los tres orígenes
de descarte ya son `GrantOpportunity` dentro de `report.opportunities` hoy). No se toca
`research/graph.py`: `result_type` (R20 de `investigador-v2`) ya se calcula y asigna:
basta con leerlo en la capa de presentación.

### Nota de numeración

Igual que el resto de specs bajo `.claude/specs/`, los requisitos `R1..` de este archivo
son locales a `descartados-filtro`; cualquier referencia a requisitos de otra spec se
cualifica explícitamente (p.ej. "R20 de `investigador-v2`", "R6 de `integracion-llm`").

---

## R1 — Persistencia de veredictos del filtro con clave URL normalizada

**Historia de usuario:** Como usuario que vuelve a abrir un informe ya generado, quiero
que el veredicto que el filtro semántico dio a cada resultado se conserve al recargar la
página, para poder ver por qué una convocatoria quedó descartada sin tener que relanzar
la investigación.

**Evidencia:** hoy el veredicto del filtro (`classify_report`, `llm/filter_report.py`)
solo vive en memoria durante la ejecución del job (`ui/jobs.py::_run_job_inner`); el
punto de lectura de la UI (`ui/app.py:320`, `report_from_dict(run.report)`) reconstruye
un `ResearchReport` que hoy no tiene ningún campo capaz de guardar esa clasificación.

Criterios de aceptación:
- 1.1 `ResearchReport` (`research/models.py`) expone un campo nuevo `filter_verdicts:
  dict[str, FilterVerdict]` — clave: URL normalizada de la oportunidad
  (`research/urlnorm.py::normalize_url`, la misma función que ya agrupa hits en
  `graph.py::_build_opportunities`); valor: el veredicto del filtro semántico para esa
  oportunidad. Por defecto, un dict vacío (`field(default_factory=dict)`).
- 1.2 Para cada oportunidad efectivamente evaluada por el filtro semántico,
  `filter_verdicts` contiene una entrada con clave `normalize_url(opportunity.url.value)`.
- 1.3 `filter_verdicts` se serializa y deserializa igual que el resto de campos del
  informe (`ui/report_serde.py::report_to_dict`/`report_from_dict`).
- 1.4 Un informe persistido **antes** de esta spec (sin la clave `filter_verdicts` en su
  JSON) se deserializa con `filter_verdicts = {}` — nunca un error, nunca un valor
  inventado.

## R2 — Distinción por origen del `no_clasificado`

**Historia de usuario:** Como usuario que revisa una convocatoria no clasificada, quiero
saber si no se clasificó porque el proveedor LLM falló (problema técnico, quizá
transitorio) o porque su respuesta no fue interpretable (problema del modelo o del
prompt), para decidir si merece la pena reintentar la investigación.

**Evidencia:** hoy ambos casos colapsan al mismo valor `"no_clasificado"`
(`llm/semantic_filter.py:36` cuando la respuesta no normaliza a SI/NO;
`llm/filter_report.py:48-58`, bloque `except LLMError`, cuando el proveedor falla) — no
hay forma de distinguirlos después del hecho (hallazgo V8 de la verificación previa).

Criterios de aceptación:
- 2.1 `ClassificationResult` pasa de 3 a 4 valores:
  `Literal["si", "no", "no_clasificado_provider", "no_clasificado_response"]`.
- 2.2 Cuando la respuesta del LLM no normaliza a "SI" ni "NO", el valor es
  `"no_clasificado_response"`.
- 2.3 Cuando la clasificación de una oportunidad falla por una excepción del proveedor
  (`LLMError` y subclases), el valor es `"no_clasificado_provider"`.
- 2.4 Ambos casos son distinguibles leyendo el valor persistido en `filter_verdicts` (R1)
  — sin necesidad de repetir la llamada al LLM.

## R3 — Sección DESCARTADOS unificada (sustituye "Material informativo")

**Historia de usuario:** Como usuario que revisa un informe, quiero ver en un solo sitio
todo lo que el sistema dejó fuera de las convocatorias activas — sea por heurística o por
filtro semántico — con el motivo de cada descarte, para no tener que adivinar por qué un
resultado no aparece en la lista principal.

Criterios de aceptación:
- 3.1 La sección "Material informativo (no convocatorias)" (hoy en
  `report_view.py:182-191`, `report_serde.py:248-255` y `report_serde.py:304-311`)
  desaparece como sección propia; su contenido (oportunidades con
  `result_type == "documento_informativo"`) se incorpora a una sección única DESCARTADOS.
- 3.2 DESCARTADOS agrupa exactamente 4 orígenes: `documento_informativo` (R20 de
  `investigador-v2`), descartada por el filtro semántico (veredicto `"no"`), no
  clasificada por fallo del proveedor (`"no_clasificado_provider"`) y no clasificada por
  respuesta inesperada (`"no_clasificado_response"`).
- 3.3 `result_type == "documento_informativo"` tiene precedencia sobre cualquier
  veredicto del filtro semántico al decidir la etiqueta mostrada — mismo comportamiento
  que ya tenía la sección "Material informativo" (que ignoraba cualquier otro criterio).
  Si en el futuro el filtro clasifica un `documento_informativo` como `"si"`, sigue
  apareciendo en DESCARTADOS con la etiqueta de heurística, no en la lista activa.
- 3.4 Una oportunidad sin entrada en `filter_verdicts` y con `result_type` distinto de
  `documento_informativo` se considera **activa** (no descartada). Cubre tres casos: sin
  Ollama disponible (el filtro nunca corrió), modo "training" (`opportunities` vacío por
  diseño) e informes persistidos antes de esta spec.
- 3.5 `result_type == "desconocido"` (R20) no se toca en esta spec: sigue mezclado con
  `convocatoria_probable` en el grupo activo, sin etiqueta ni distinción — ver "Fuera de
  alcance".

## R4 — Sección DESCARTADOS en vista resumida

**Historia de usuario:** Como usuario que descarga el resumen del informe, quiero que
incluya también lo descartado con su motivo, para no perder esa información en la
versión abreviada.

Criterios de aceptación:
- 4.1 `report_to_markdown_summary` (`report_serde.py:274-325`) incluye una sección
  DESCARTADOS con título, URL y etiqueta de motivo (R8) por cada oportunidad descartada.
- 4.2 Si no hay ninguna oportunidad descartada, la sección no aparece en el Markdown
  generado.

## R5 — Sección DESCARTADOS en vista detallada

**Historia de usuario:** Como usuario que quiere el detalle completo del informe, quiero
ver la sección DESCARTADOS junto al resto de datos, con el mismo nivel de detalle que las
demás secciones del informe completo.

Criterios de aceptación:
- 5.1 `report_to_markdown` (`report_serde.py:223-271`) incluye la misma sección
  DESCARTADOS que la vista resumida (R4), en el mismo formato (título, URL, etiqueta).
- 5.2 Si no hay ninguna oportunidad descartada, la sección no aparece.

## R6 — Sección DESCARTADOS en la descarga .md (ambos botones)

**Historia de usuario:** Como usuario que descarga el informe, quiero que tanto el
archivo resumen como el detallado incluyan DESCARTADOS, para tener la misma información
disponible sin depender de la vista en pantalla.

Criterios de aceptación:
- 6.1 Los dos botones de descarga de `report_view.py` (`col_resumen`/`col_detalle`,
  líneas 213-227) usan `report_to_markdown_summary`/`report_to_markdown` sin cambios de
  cableado — automáticamente incluyen DESCARTADOS al cumplirse R4/R5.
- 6.2 El expander "Ver informe detallado" (`report_view.py:208-209`), que reutiliza
  `report_to_markdown`, muestra DESCARTADOS igual que la descarga detallada (mismo
  contenido, R22.4 de `streamlit`: "se genera del mismo informe que la vista detallada").

## R7 — UI Streamlit: expandible colapsado al final con contador

**Historia de usuario:** Como usuario que revisa un informe en pantalla, quiero que lo
descartado esté disponible pero no estorbe la vista principal, con un contador que me
diga de un vistazo cuánto hay sin tener que abrirlo.

Criterios de aceptación:
- 7.1 `render_report` (`report_view.py:123-230`) muestra la sección DESCARTADOS como un
  `st.expander` colapsado por defecto (`expanded=False`), situado al final del
  renderizado — después de "Datos por confirmar" (líneas 193-196) y "Fuentes con
  problemas" (líneas 198-203), antes del expander "Ver informe detallado".
- 7.2 El título del expandible incluye un contador explícito: `"DESCARTADOS: N"`, con `N`
  = número total de oportunidades descartadas (suma de los 4 orígenes de R3.2).
- 7.3 La sección no se renderiza (ni expandible ni contador) si `N == 0`.
- 7.4 Dentro del expandible, cada descartada muestra título, URL y etiqueta de motivo
  (R8) — sin importe/plazo/organismo ni ninguna acción sobre ella (ver "Fuera de
  alcance": sin rescate en esta spec).

## R8 — Etiquetas concretas por origen

**Historia de usuario:** Como usuario que lee la sección DESCARTADOS, quiero una frase
clara y concreta para cada motivo de descarte, no un código interno, para entender sin
tener que consultar documentación aparte.

Criterios de aceptación:
- 8.1 Veredicto `"no"` del filtro semántico → **"Descartada por filtro semántico"**.
- 8.2 Veredicto `"no_clasificado_provider"` → **"No clasificada (fallo del proveedor
  LLM)"**.
- 8.3 Veredicto `"no_clasificado_response"` → **"No clasificada (respuesta inesperada del
  LLM)"**.
- 8.4 `result_type == "documento_informativo"` (R20) → **"Documento informativo
  (heurística)"**.
- 8.5 Las 4 etiquetas son el único texto de motivo mostrado — se usan literalmente,
  iguales en las 3 vistas (resumida, detallada, Streamlit en vivo).

## R9 — Testing

**Historia de usuario:** Como desarrollador que mantiene esta funcionalidad, quiero
cobertura automática de los 4 orígenes de descarte, del caso sin descartes y de la
retrocompatibilidad con informes antiguos, para poder refactorizar sin miedo a
romper silenciosamente la sección DESCARTADOS.

Criterios de aceptación:
- 9.1 Existe un test que cubre cada uno de los 4 orígenes de descarte por separado,
  verificando que produce la etiqueta correcta (R8).
- 9.2 Existe un test del caso "sin descartes" (todas las oportunidades activas): ni la
  sección Streamlit ni las secciones Markdown se renderizan/incluyen (R3.4, R4.2, R5.2,
  R7.3).
- 9.3 Existe un test de retrocompatibilidad: un informe con `opportunities` que incluyen
  un `documento_informativo` pero **sin** la clave `filter_verdicts` en el dict
  persistido (formato pre-spec) se deserializa con `filter_verdicts = {}` y aun así
  muestra el `documento_informativo` en DESCARTADOS, sin mostrar ningún descarte por
  filtro inventado (R1.4, R3.4).
- 9.4 Existe al menos un test que ejercita las 3 vistas (resumida, detallada, Streamlit
  en vivo) sobre el mismo informe de prueba y verifica que las 3 coinciden en qué está
  descartado y con qué etiqueta.

---

## Fuera de alcance

- **Rescate desde la UI:** mover una oportunidad descartada de vuelta a activa
  (revalidación de plazo, persistencia del rescate en SQLite). Registrado como idea de
  producto futura en `Contexto_para_mi/ideas_producto.md` ("Rescate de descartados desde
  UI"), condicionada al cierre de esta spec.
- **Iteración del prompt `semantic_filter.md`:** sustituida por esta spec (cierre de la
  decisión pendiente #22). El prompt actual queda sin cambios.
- **Reubicación de `result_type == "desconocido"`:** sigue mezclado con
  `convocatoria_probable` en el grupo activo (R3.5). Se abordará en una spec/reapertura
  aparte solo si aparece evidencia empírica de que conviene distinguirlo.
- **Cambio del gating R23.3 de `investigador-v2`** (`research/graph.py`, lectura profunda
  solo para `convocatoria_probable`): `documento_informativo` nunca entró a esa lectura
  profunda y esta spec no lo cambia.
- **Cualquier cambio en `research/graph.py` o `research/triage.py`:** `result_type` ya se
  calcula y asigna correctamente (R20); esta spec solo lo lee en la capa de presentación.
