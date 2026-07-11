# Design Document — descartados-filtro

## Overview

Spec de **presentación**, no estructural: no se crea ningún modelo de dominio nuevo. Los
tres orígenes de descarte (heurística R20, "NO" del filtro semántico, no-clasificado por
dos motivos distintos) ya son `GrantOpportunity` dentro de `report.opportunities` hoy —
lo único que falta es (a) un lugar donde persistir el veredicto del filtro semántico por
oportunidad y (b) una capa de presentación que lea `result_type` + ese veredicto y decida
qué mostrar como activo y qué mostrar como descartado, con qué etiqueta.

No se toca `research/graph.py` ni `research/triage.py`: R20 (`result_type`) ya se calcula
y asigna correctamente (`graph.py:421`, `graph.py:432`); esta spec solo lo lee.

## Hallazgo clave de la verificación previa (V1-V8) que reformula el alcance

La verificación previa a esta spec encontró que **hoy la UI ni siquiera lee** los
buckets `discarded`/`unclassified` que ya persiste `llm/enrichment_serde.py` (T11 de
`integracion-llm`): `ui/app.py:320` reconstruye el informe con
`report_from_dict(run.report)` (la función "plana" de `ui/report_serde.py`), que ignora
silenciosamente las claves extra (`discarded`, `unclassified`, `semantic_filter_applied`)
que añade `enriched_report_to_dict`. Solo `scripts/verificacion_t13.py` (script temporal,
decisión #24 pendiente) lee esas claves, con `enriched_report_from_dict`.

**Consecuencia de diseño:** en vez de mantener dos estructuras paralelas (los 3 buckets
de `EnrichedReport` por un lado, `filter_verdicts` por otro), esta spec **simplifica
`EnrichedReport`**: sus campos `discarded`/`unclassified` desaparecen — la información que
aportaban (qué oportunidad fue descartada y con qué veredicto) pasa a vivir como
`filter_verdicts` en el propio `ResearchReport`, que SÍ se serializa/deserializa con las
funciones que `ui/app.py:320` ya usa sin cambios. Esto resuelve de paso el hueco de
lectura descrito arriba, sin tocar `app.py`.

`EnrichedReport` queda reducido a `base: ResearchReport` + `semantic_filter_applied:
bool` — sigue existiendo porque `semantic_filter_applied` no tiene un hogar natural en
`ResearchReport` (research/ no debe saber que existe un filtro semántico, ver más abajo);
pero ya no hace falta que separe listas de oportunidades, porque `base.opportunities`
ahora conserva **todas** las oportunidades (activas y descartadas) — la separación para
mostrar es responsabilidad exclusiva de la capa de presentación (R3).

## Decisiones de diseño por requisito

### R1 — Persistencia de `filter_verdicts`

**Dónde:** `research/models.py:236-246` (`ResearchReport`).

- **Tipo del campo — aclaración necesaria sobre el boundary `llm/` → `research/`:** el
  valor de cada entrada NO es el `ClassificationResult` importado de `llm/`
  (`llm/semantic_filter.py`/`llm/filter_report.py`) — eso violaría la Opción B (decisión
  #8 de T8 de `integracion-llm`, reafirmada en la reapertura R7: `research/` no debe
  importar nada de `llm/`). En vez de eso, `research/models.py` define su **propio**
  `Literal` local, mismo patrón que ya usa `ResultType` (`models.py:30`):

  ```python
  # Veredicto persistido del filtro semántico (llm/, spec descartados-filtro). Mismos 4
  # valores que ClassificationResult de llm/semantic_filter.py — Literal local, no
  # importado: research/ no debe conocer la existencia del filtro (Opción B, decisión #8
  # de integracion-llm). En Python los Literal de string son estructurales: ambos módulos
  # usan las mismas 4 cadenas sin acoplarse por import.
  FilterVerdict = Literal["si", "no", "no_clasificado_provider", "no_clasificado_response"]
  ```

  Precedente ya existente en el repo para esta misma técnica de "mismo Literal, definido
  dos veces, sin import cruzado": `ClassificationResult` ya está duplicado hoy entre
  `llm/semantic_filter.py:17` y `llm/filter_report.py:26` (ambos dentro de `llm/`, pero
  confirma que el proyecto ya acepta esta redundancia deliberada en vez de forzar un
  import compartido cuando hay un boundary de por medio).

- **Campo nuevo:**
  ```python
  filter_verdicts: dict[str, FilterVerdict] = field(default_factory=dict)
  ```
  añadido a `ResearchReport` junto a `failed_sources` (última línea del dataclass,
  `models.py:245`).

- **Clave:** `normalize_url(opportunity.url.value)`, usando
  `research/urlnorm.py::normalize_url` — la misma función que `graph.py:384` ya usa para
  agrupar hits en `_build_opportunities`. Si `opportunity.url.value` es `None`,
  `normalize_url(None)` devuelve `""` (urlnorm.py:31-32); en la práctica esto no genera
  colisiones porque toda oportunidad construida por el investigador procede de un grupo
  de hits con URL no vacía (`graph.py:401`, `url_val = group[0].url`). Se documenta como
  límite conocido, no se blinda explícitamente (no hay caso real que lo dispare).

- **Población del dict:** en `llm/enrichment.py::enrich_report` (línea 57, donde ya se
  invoca `classify_report`) — ver sección "Puntos de conexión" más abajo.

- **Serialización:** `ui/report_serde.py::report_to_dict`/`report_from_dict`
  (líneas 34-49 y 106-122) ganan una clave `filter_verdicts` más, con el mismo patrón
  retrocompatible que ya usa `result_type` en `opp_from_dict` (línea 132,
  `data.get("result_type", "desconocido")`): `data.get("filter_verdicts", {})`.

### R2 — `ClassificationResult` ampliado a 4 valores

**Dónde:** `llm/semantic_filter.py:17` y `llm/filter_report.py:26` (las dos
definiciones locales del `Literal`, ver nota de R1 sobre por qué están duplicadas).

- Ambas pasan de `Literal["si", "no", "no_clasificado"]` a
  `Literal["si", "no", "no_clasificado_provider", "no_clasificado_response"]`.
- `llm/semantic_filter.py::classify_result`, línea 36: el `return "no_clasificado"` final
  (cuando `normalized` no es `"SI"` ni `"NO"`) pasa a `return "no_clasificado_response"`.
  Es la única línea de lógica que cambia en esa función.
- `llm/filter_report.py::classify_report`, líneas 50-58 (bloque `except LLMError`): la
  asignación `results[id(opportunity)] = "no_clasificado"` pasa a
  `"no_clasificado_provider"`. Es la única línea de lógica que cambia en esa función.
- **Impacto en tests existentes** (deben adaptarse, no son parte del alcance funcional
  pero sí de la tarea que toca estas líneas):
  - `tests/llm/test_semantic_filter.py::test_classify_result_defaults_to_no_clasificado`
    (líneas 45-58): la aserción `== "no_clasificado"` pasa a
    `== "no_clasificado_response"`; renombrar el test a
    `test_classify_result_defaults_to_no_clasificado_response`.
  - `tests/llm/test_filter_report.py`: 3 aserciones a actualizar —
    `test_classify_report_maps_each_opportunity_id_to_its_classification` (línea 64,
    `"basura"` → hoy `"no_clasificado"`, pasa a `"no_clasificado_response"`),
    `test_classify_report_isolates_failures_and_continues` (línea 85, el resultado del
    fallo de conexión pasa de `"no_clasificado"` a `"no_clasificado_provider"`),
    `test_classify_report_logs_warning_on_llm_error` (no cambia la aserción del log, pero
    queda como referencia cruzada de que ese camino es justo el que ahora se llama
    `"no_clasificado_provider"`).

### R3/R8 — Función clasificadora para la vista

**Dónde:** módulo nuevo helper dentro de `ui/report_serde.py` (NO en `report_view.py`).

**Por qué `report_serde.py` y no `report_view.py`:** `report_serde.py` ya es la capa pura
sin Streamlit ("Solo conoce los modelos públicos del investigador; no usa Streamlit ni
SQLite", docstring línea 8) de la que `report_view.py` importa funciones (`opportunity_numbers`,
`report_to_markdown`, `report_to_markdown_summary`, `url_verification_suffix`, línea 19).
La función clasificadora la necesitan **ambos** consumidores — el Markdown (R4/R5, en
`report_serde.py` mismo) y el render Streamlit (R7, en `report_view.py`) — así que vive
donde ya vive todo lo que ambos comparten, siguiendo la dirección de dependencia
existente (`report_view.py` → `report_serde.py`, nunca al revés).

```python
DisplayStatus = Literal[
    "activa",
    "descartada_filtro",
    "no_clasificada_provider",
    "no_clasificada_response",
    "documento_informativo",
]

DISCARD_LABELS: dict[str, str] = {
    "descartada_filtro": "Descartada por filtro semántico",
    "no_clasificada_provider": "No clasificada (fallo del proveedor LLM)",
    "no_clasificada_response": "No clasificada (respuesta inesperada del LLM)",
    "documento_informativo": "Documento informativo (heurística)",
}


def classify_for_display(
    opportunity: GrantOpportunity, filter_verdicts: dict[str, str]
) -> DisplayStatus:
    """Decide cómo presentar una oportunidad: activa o descartada (con motivo, R3/R8).

    `documento_informativo` (R20) tiene precedencia sobre cualquier veredicto del filtro
    semántico (R3.3): mismo comportamiento que ya tenía la sección "Material informativo"
    que esta función sustituye.
    """
    if opportunity.result_type == "documento_informativo":
        return "documento_informativo"
    verdict = filter_verdicts.get(normalize_url(opportunity.url.value or ""))
    if verdict == "no":
        return "descartada_filtro"
    if verdict == "no_clasificado_provider":
        return "no_clasificada_provider"
    if verdict == "no_clasificado_response":
        return "no_clasificada_response"
    return "activa"  # "si", ausencia de veredicto (sin Ollama/training/informe viejo)


def partition_by_discard_status(
    opportunities: list[GrantOpportunity], filter_verdicts: dict[str, str]
) -> tuple[list[GrantOpportunity], list[tuple[GrantOpportunity, DisplayStatus]]]:
    """Separa activas de descartadas; cada descartada va con su `DisplayStatus` (R3)."""
    active: list[GrantOpportunity] = []
    discarded: list[tuple[GrantOpportunity, DisplayStatus]] = []
    for opp in opportunities:
        status = classify_for_display(opp, filter_verdicts)
        if status == "activa":
            active.append(opp)
        else:
            discarded.append((opp, status))
    return active, discarded
```

`partition_by_discard_status` **sustituye** a `partition_by_actionability`
(`report_view.py:44-55`), que hoy solo mira `result_type` y no conoce `filter_verdicts`.
Requiere `normalize_url` importado de `research/urlnorm.py` en `report_serde.py` (mismo
sentido de dependencia `ui/` → `research/` que ya usa el resto del módulo).

### R4/R5/R6 — Refactor de las vistas Markdown

**Dónde:** `report_serde.py::report_to_markdown` (líneas 223-271) y
`report_to_markdown_summary` (líneas 274-325).

En ambas funciones, sustituir el par de líneas:
```python
actionable = [o for o in report.opportunities if o.result_type != "documento_informativo"]
informational = [o for o in report.opportunities if o.result_type == "documento_informativo"]
```
(líneas 227-228 y 281-282) por:
```python
actionable, discarded = partition_by_discard_status(report.opportunities, report.filter_verdicts)
```

Y sustituir el bloque `if informational:` (líneas 248-255 en `report_to_markdown`,
304-311 en `report_to_markdown_summary`) por una sección única:
```python
if discarded:
    lines.append(f"## Descartados ({len(discarded)})")
    lines.append("")
    for opp, status in discarded:
        title = opp.title.value or "(sin título)"
        url = opp.url.value
        label = DISCARD_LABELS[status]
        entry = f"[{title}]({url})" if url else title
        lines.append(f"- {entry} — {label}")
    lines.append("")
```
Nota de estilo: el encabezado Markdown usa capitalización de frase (`## Descartados`),
igual que el resto de encabezados del documento (`## Convocatorias`, `## Datos por
confirmar`); el formato en mayúsculas `"DESCARTADOS: N"` es específico del expandible de
Streamlit (R7.2), no del Markdown.

### R7 — Refactor de `render_report` (Streamlit)

**Dónde:** `report_view.py::render_report` (líneas 123-230).

- Línea 19: importar `partition_by_discard_status` y `DISCARD_LABELS` (dict público,
  ver R3/R8) además de lo ya importado
  (`opportunity_numbers, report_to_markdown, report_to_markdown_summary,
  url_verification_suffix`).
- Líneas 132-134: sustituir la llamada a `partition_by_actionability(ordered)` por
  `partition_by_discard_status(ordered, report.filter_verdicts)`, ajustando el nombre de
  la segunda variable (`informational` → `discarded`, ahora una lista de tuplas
  `(opp, status)` en vez de una lista plana de oportunidades).
- Líneas 182-191 (bloque `if informational: st.subheader("Material informativo...")`):
  se elimina y se sustituye por un bloque nuevo, colocado DESPUÉS del bloque de
  `failed_sources` (línea 203) y ANTES del expander "Ver informe detallado" (línea 205),
  para cumplir el orden de R7.1:
  ```python
  if discarded:
      with st.expander(f"DESCARTADOS: {len(discarded)}", expanded=False):
          for opp, status in discarded:
              title = opp.title.value or "(sin título)"
              url = opp.url.value
              label = DISCARD_LABELS[status]  # importado de report_serde.py
              entry = f"[{title}]({url})" if url else title
              st.markdown(f"- {entry} — {label}")
  ```

### Numeración — `opportunity_numbers`

**Dónde:** `report_serde.py::opportunity_numbers` (líneas 202-220).

La condición de exclusión (línea 217, hoy `if opp.result_type != "documento_informativo"`)
pasa a usar la misma función clasificadora, para que los 4 orígenes de descarte (no solo
`documento_informativo`) queden sin número:
```python
def opportunity_numbers(report: ResearchReport) -> dict[int, int]:
    numbers: dict[int, int] = {}
    n = 0
    for opp in report.opportunities:
        if classify_for_display(opp, report.filter_verdicts) == "activa":
            n += 1
            numbers[id(opp)] = n
    return numbers
```
La firma pública no cambia (sigue recibiendo solo `report`); el efecto observable sí
cambia: antes, una oportunidad descartada por el filtro semántico SÍ recibía número (el
filtro semántico no existía como concepto para esta función); ahora no lo recibe, de
forma coherente con que ya no aparece en la lista de convocatorias activas.

### Puntos de conexión — `llm/enrichment.py` (población de `filter_verdicts`)

**Dónde:** `llm/enrichment.py::enrich_report` (líneas 33-76), único punto donde hoy se
invoca `classify_report` (línea 57).

Cambio de forma: `EnrichedReport` pierde `discarded`/`unclassified` (ver "Hallazgo
clave" arriba); `enrich_report` deja de dividir `report.opportunities` en 3 listas y en
su lugar construye `filter_verdicts` y lo adjunta a `base` sin tocar la lista de
oportunidades:

```python
@dataclass
class EnrichedReport:
    """`ResearchReport` con clasificación semántica opcional aplicada.

    `base.opportunities` conserva TODAS las oportunidades (activas y descartadas): la
    separación para mostrar es responsabilidad de la capa de presentación
    (`ui/report_serde.py::classify_for_display`, spec `descartados-filtro`), no de esta
    capa de orquestación.
    """

    base: ResearchReport
    semantic_filter_applied: bool


def enrich_report(report: ResearchReport, provider: LLMProvider | None) -> EnrichedReport:
    if provider is None:
        return EnrichedReport(base=report, semantic_filter_applied=False)

    classifications = classify_report(provider, report)
    verdicts = {
        normalize_url(opp.url.value or ""): classifications[id(opp)]
        for opp in report.opportunities
        if id(opp) in classifications
    }
    return EnrichedReport(
        base=replace(report, filter_verdicts=verdicts),
        semantic_filter_applied=True,
    )
```

`normalize_url` se importa de `research/urlnorm.py` (mismo sentido de dependencia
`llm/` → `research/` ya vigente en este módulo). `ui/jobs.py::_run_job_inner` (líneas
182-184) **no cambia**: sigue llamando `enrich_report(report, provider)` y
`enriched_report_to_dict(enriched)` exactamente igual; solo cambia lo que hay dentro de
`EnrichedReport`.

`llm/enrichment_serde.py` se simplifica en consecuencia: `enriched_report_to_dict`/
`enriched_report_from_dict` dejan de serializar `discarded`/`unclassified` (ya no
existen) — solo añaden/leen la clave `semantic_filter_applied` sobre el dict que ya
produce `report_to_dict(enriched.base)` (que ahora incluye `filter_verdicts` gracias a
R1). El resultado neto es un módulo más corto, no una reescritura conceptual.

**Nota sobre `scripts/verificacion_t13.py`:** este script temporal (decisión #24
pendiente, no comiteado) usa `enriched_report_from_dict` y accede a
`enriched.discarded`/`enriched.unclassified` (líneas 33-37, 48-50) — dejará de funcionar
tal cual tras T3. Al ser un script de apoyo puntual y no comiteado, no se adapta como
parte de esta spec; si se decide conservarlo (decisión #24), se actualiza o se sustituye
por lectura directa de `report.filter_verdicts` en ese momento.

### Retrocompatibilidad SQLite

Dos mecanismos, ya cubiertos por R1.4/R3.4, sin necesidad de migración de datos:

1. **Informes pre-`integracion-llm` o pre-`descartados-filtro`** (sin `filter_verdicts`
   en el JSON persistido): `report_from_dict` los reconstruye con `filter_verdicts = {}`
   (`data.get("filter_verdicts", {})`). Sus `documento_informativo` (si los tienen, ya
   que `result_type` es retrocompatible desde R20) siguen apareciendo en DESCARTADOS —
   correcto, porque la heurística R20 es independiente del filtro semántico y ya estaba
   persistida. Ningún descarte por filtro aparece — también correcto: para esos informes
   el filtro semántico nunca corrió.
2. **Informes de la ventana T11-T13 de `integracion-llm`** (con `discarded`/
   `unclassified`/`semantic_filter_applied` en formato antiguo de
   `enriched_report_to_dict`, pero sin `filter_verdicts`): `report_from_dict` (la función
   que de hecho usa `ui/app.py:320`) ya ignora esas 3 claves hoy — sigue ignorándolas tras
   esta spec. Sus oportunidades descartadas por el filtro en aquella ventana NO
   reaparecen en DESCARTADOS (no hay veredicto que leer), pero tampoco se pierden datos
   nuevos: es el mismo comportamiento que tenían antes de esta spec (esas oportunidades
   ya eran invisibles en la UI, ver "Hallazgo clave"). No se considera una regresión.

No se necesita migración de datos activa (sin `ALTER`, sin script de backfill): el patrón
retrocompatible ya establecido por R20 (`opp_from_dict`, línea 132) se reutiliza
literalmente igual para `filter_verdicts`.

## Testing strategy

- **R1/T2:** `tests/ui/test_report_serde.py` — round-trip de `filter_verdicts` (dict no
  vacío, serializa y deserializa igual); deserialización de un dict SIN la clave
  `filter_verdicts` → `{}` sin error.
- **R2/T1:** `tests/llm/test_semantic_filter.py` y `tests/llm/test_filter_report.py` —
  adaptar las aserciones existentes a los 2 valores nuevos (ver lista exacta en la
  sección R2 de arriba); ningún test nuevo de comportamiento, solo el valor esperado
  cambia de nombre.
- **R3/R8/T4:** módulo de test para `classify_for_display` (nuevo bloque en
  `tests/ui/test_report_serde.py`, o archivo nuevo `test_report_serde_discard.py` si se
  prefiere aislar — decisión menor de organización al implementar) — 5 casos: `"si"` →
  activa, ausencia de veredicto → activa, `"no"` → descartada_filtro,
  `"no_clasificado_provider"` → no_clasificada_provider, `"no_clasificado_response"` →
  no_clasificada_response; más 1 caso de precedencia: `documento_informativo` con
  veredicto `"si"` → sigue siendo `documento_informativo` (R3.3).
- **R4/R5/R6/T5:** `tests/ui/test_report_serde.py` — las pruebas actuales que buscan
  `"Material informativo"` en el Markdown (líneas 205, 253, 262) se reemplazan por
  pruebas que buscan `"Descartados"` y las 4 etiquetas exactas de R8; prueba de "sin
  descartes" → sección ausente en ambas vistas Markdown.
- **T3 (`llm/enrichment.py`):** `tests/llm/test_enrichment.py` se reescribe: las
  aserciones sobre `enriched.discarded`/`enriched.unclassified` (líneas 62-63, 79-84,
  100-104, 116-118, 129-132) se sustituyen por aserciones sobre
  `enriched.base.opportunities == report.opportunities` (ya no se filtra nada) y
  `enriched.base.filter_verdicts` (dict con las claves de URL normalizada esperadas).
  `tests/llm/test_enrichment_serde.py` se reescribe en paralelo: sin `discarded`/
  `unclassified` que serializar, sus 4 tests actuales colapsan a un round-trip de
  `EnrichedReport` (`base` + `semantic_filter_applied`) más un test de que
  `filter_verdicts` sobrevive dentro de `base`.
- **R7/T6:** `tests/ui/test_report_view.py` — las pruebas actuales de
  `partition_by_actionability` (líneas 153-166, 191) se adaptan a
  `partition_by_discard_status` (firma con 2 argumentos); prueba nueva del contador
  `"DESCARTADOS: N"` y de que el expandible no aparece con `N == 0`. Verificación del
  expandible en pantalla: smoke test con `AppTest` en `tests/ui/test_app_smoke.py` si se
  considera necesario cubrir el render real (patrón ya usado en T12 para el warning de
  Ollama), o cobertura suficiente vía las funciones puras si el equipo lo considera
  redundante — decisión menor al implementar T6.
- **R9/T7 (end-to-end):** `tests/ui/test_jobs.py`, reutilizando el patrón de
  `_SequenceLLMProvider`/`_SequencedProvider` ya usado en `test_filter_report.py`/
  `test_enrichment.py` para simular una investigación con las 4 oportunidades (una por
  origen de descarte) en una sola pasada por `_run_job_inner`; verificar que el run
  persistido, releído con `report_from_dict` (el mismo camino que usa `ui/app.py:320`),
  reproduce las 4 etiquetas correctas vía `classify_for_display`. Caso adicional: mismo
  flujo sin Ollama disponible (`is_ollama_available` mockeado a `False`) con al menos un
  `documento_informativo` en el informe — debe aparecer en DESCARTADOS pese a
  `semantic_filter_applied=False` (R3.4).

**Explícitamente fuera de la cobertura automatizada:** la calidad real de clasificación
del LLM (si distingue bien un caso ambiguo) sigue sin testear con datos reales — eso ya
estaba fuera de alcance en `integracion-llm` y no cambia aquí; esta spec solo cubre cómo
se presenta el resultado, sea cual sea.

## Orden de implementación y dependencias

`ClassificationResult` ampliado (R2, independiente) → `filter_verdicts` en
`ResearchReport` + serialización (R1, necesita R2 para tipar los valores posibles) →
población en `enrich_report` (conecta R1 y R2) → función clasificadora de la vista (R3/R8,
necesita R1 para leer `filter_verdicts`) → refactor Markdown (R4/R5/R6, usa la función
clasificadora) → refactor Streamlit (R7, usa la misma función + reutiliza el refactor de
numeración) → end-to-end (R9, ejercita toda la cadena). Coincide con el orden T1→T7 de
`tasks.md`.
