# Spec alineacion-estrategica — requirements.md

## Origen

**Motivo:** las convocatorias de cooperación internacional en España se evalúan mediante
baremos que puntúan la alineación del proyecto con la nomenclatura oficial del Plan
Director de la Cooperación Española 2024-2027. Los evaluadores usan herramientas
automatizadas que detectan coincidencia literal con esa nomenclatura; sinónimos o
variantes penalizan.

Actualmente el modelo `Opportunity` no captura esta alineación estratégica. El
investigador encuentra convocatorias y las clasifica como relevantes o no mediante el
filtro semántico, pero no extrae con qué ODS, qué región prioritaria, qué enfoques
transversales y qué sectores del Plan Director están alineadas.

Esta spec fusiona las decisiones pendientes **#16** (campos ODS en `Opportunity`) y
**#27** (alineación con el Plan Director), cuyo diseño se acordó el 16-07-2026 (ver
`Contexto_para_mi/notas_spec4.md`, sección "Decisión de diseño del 16-07-2026 (#16 +
#27)"; ambas entradas siguen marcadas como "Diseño acordado" en
`decisiones_pendientes.md`, no cerradas, a la espera de esta spec). El borrador de esta
spec se redacta el 17-07-2026.

Esta spec añade la capacidad de alineación estratégica al pipeline del investigador,
poblando el modelo `Opportunity` con cuatro campos extraídos automáticamente mediante
LLM local (Ollama) durante la fase de enrichment, justo después del filtro semántico y
solo para las convocatorias que ese filtro considera relevantes.

### Nota de numeración

Igual que el resto de specs bajo `.claude/specs/`, los requisitos `R1..` de este archivo
son locales a `alineacion-estrategica`; cualquier referencia a requisitos de otra spec se
cualifica explícitamente.

---

## R1 — Modelo de datos: cuatro campos de alineación estratégica

**Nota (2026-07-20):** no existe un modelo `Opportunity` en el proyecto (ver `design.md`,
sección "Modelo de datos"). Los cuatro campos se agrupan en un contenedor nuevo,
`AlineacionEstrategica`, independiente de `GrantOpportunity`/`research/models.py`.

Se define un contenedor `AlineacionEstrategica` con cuatro campos nuevos que
representan la alineación de la convocatoria con el marco estratégico oficial
de la cooperación española.

- `ods: list[int]` — números de los ODS (1-17) a los que la convocatoria contribuye.
  Lista plana sin distinción principal/secundario.
- `prioridades_geograficas: list[str]` — regiones prioritarias del Plan Director
  a las que la convocatoria se dirige.
- `enfoques_transversales: list[str]` — enfoques transversales obligatorios
  del Plan Director que la convocatoria incorpora.
- `sectores_plan_director: list[str]` — sectores del Plan Director en los que
  la convocatoria se enmarca.

### Criterios de aceptación

- Los cuatro campos existen en `AlineacionEstrategica` con los tipos indicados.
- Los cuatro campos tienen default `[]` (lista vacía). Convocatorias anteriores
  a esta spec cargan sin error y aparecen como "no alineadas".
- La serialización y deserialización preservan las cuatro listas.
- Los valores de `prioridades_geograficas`, `enfoques_transversales` y
  `sectores_plan_director` proceden exclusivamente de sus catálogos YAML
  correspondientes; cualquier valor fuera del catálogo se descarta al parsear
  la respuesta del LLM (ver R5).

## R2 — Catálogo de prioridades geográficas

Existe un catálogo YAML `prioridades_geograficas.yaml` con las cuatro regiones
prioritarias oficiales del Plan Director 2024-2027.

Valores:

- América Latina y el Caribe
- Norte de África
- Oriente Próximo
- África Subsahariana

Fuente: Plan Director de la Cooperación Española para el Desarrollo Sostenible
y la Solidaridad Global 2024-2027, NIPO 108240367, sección 3.3.

### Criterios de aceptación

- El archivo `prioridades_geograficas.yaml` existe en la ubicación definida por
  el `design.md` y contiene los cuatro valores literales indicados.
- El catálogo se carga sin error y expone una función pura que devuelve la
  lista de valores válidos.
- Los tests unitarios verifican: carga correcta, no duplicados, coincidencia
  literal con la fuente oficial.

## R3 — Catálogo de enfoques transversales

Existe un catálogo YAML `enfoques_transversales.yaml` con los seis enfoques
transversales oficiales del Plan Director 2024-2027.

Valores:

- Enfoque de derechos humanos
- Enfoque feminista y de género
- Enfoque de lucha contra la pobreza y las desigualdades
- Enfoque de justicia climática y sostenibilidad medioambiental
- Enfoque de diversidad cultural
- Enfoque de construcción de paz

Fuente: Plan Director 2024-2027, sección 3.1 (subsecciones 3.1.1 a 3.1.6).

### Criterios de aceptación

- El archivo `enfoques_transversales.yaml` existe y contiene los seis valores
  literales indicados.
- El catálogo se carga sin error y expone una función pura análoga a la de R2.
- Los tests unitarios verifican: carga correcta, no duplicados, coincidencia
  literal con la fuente oficial.

## R4 — Catálogo jerárquico de sectores del Plan Director

Existe un catálogo YAML `sectores_plan_director.yaml` con los trece sectores
oficiales del Plan Director 2024-2027, organizados jerárquicamente por
transición.

Cada sector tiene: nombre oficial, transición a la que pertenece, y ODS de
referencia.

**Transición social** (6 sectores):

| Sector | ODS |
|---|---|
| Gobernabilidad democrática | 16 |
| Salud global y sistemas sanitarios | 3 |
| Seguridad alimentaria y lucha contra el hambre | 2 |
| Educación equitativa, inclusiva y de calidad y formación a lo largo de la vida | 4 |
| Igualdad de género y empoderamiento de todas las mujeres, niñas y adolescentes | 3, 5, 10, 16 |
| Cultura y desarrollo | 11 |

**Transición ecológica** (4 sectores):

| Sector | ODS |
|---|---|
| Lucha contra el cambio climático: adaptación y mitigación | 13 |
| Acceso a energías limpias | 7 |
| Promoción y protección de la biodiversidad | 14, 15 |
| Agua y saneamiento | 6 |

**Transición económica** (3 sectores):

| Sector | ODS |
|---|---|
| Desarrollo rural territorial y sistemas agroalimentarios sostenibles | 2, 11, 14 |
| Desarrollo económico inclusivo y sostenible | 8, 9, 12 |
| Digitalización para el desarrollo sostenible | 4, 9, 16 |

Fuente: Plan Director 2024-2027, secciones 3.2.1, 3.2.2 y 3.2.3.

### Criterios de aceptación

- El archivo `sectores_plan_director.yaml` existe y contiene los trece
  sectores con nombre literal, transición y lista de ODS.
- El modelo `Opportunity` guarda únicamente los nombres de sector en su campo
  `sectores_plan_director`; la transición se deriva del catálogo cuando se
  necesita.
- El catálogo expone: una función que devuelve la lista de sectores válidos,
  y una función que dado un sector devuelve su transición.
- Los tests unitarios verifican: carga correcta, trece sectores, no duplicados,
  coincidencia literal con la fuente oficial, cada sector pertenece a exactamente
  una transición, la función de derivación de transición es correcta para los
  trece.

## R5 — Parser de la respuesta del LLM

Existe un parser que toma la respuesta cruda del LLM extractor (JSON plano con
los cuatro campos, ver R6) y devuelve los cuatro campos ya validados contra
sus catálogos.

Comportamiento del parser:

- Si un valor extraído por el LLM no coincide literalmente con ningún valor
  del catálogo correspondiente, ese valor se descarta y se registra un log
  a nivel WARNING con el valor rechazado y el catálogo esperado.
- Los ODS se validan como enteros entre 1 y 17 inclusive; enteros fuera de
  rango se descartan con log WARNING.
- El parser nunca lanza excepción por valores fuera de taxonomía. Solo lanza
  excepción si la respuesta del LLM no es JSON parseable o no tiene la
  estructura esperada de los cuatro campos.
- Duplicados dentro de una lista se colapsan a valor único preservando el
  orden de primera aparición.

### Criterios de aceptación

- Dado un JSON válido con valores todos en catálogo, el parser devuelve los
  cuatro campos íntegros.
- Dado un JSON con algunos valores fuera de catálogo, el parser devuelve los
  válidos y descarta los inválidos, emitiendo log WARNING por cada descarte.
- Dado un JSON con estructura corrupta o no parseable, el parser lanza una
  excepción específica que el pipeline sabe capturar (ver R7).
- Los tests unitarios cubren: caso feliz, valores fuera de catálogo, ODS fuera
  de rango, duplicados, JSON malformado, estructura incorrecta.

## R6 — Prompt de extracción de alineación estratégica

Existe un prompt LLM en `src/agente_ong/llm/prompts/opportunity_alignment.md`
que toma como entrada el texto de una convocatoria y devuelve un JSON plano
con los cuatro campos de alineación estratégica.

El prompt:

- Recibe la taxonomía completa (los cuatro catálogos) inyectada en su cuerpo,
  como lista de valores permitidos por campo.
- Instruye al LLM a devolver **solo** valores literales de esa taxonomía, sin
  parafrasear ni inventar sinónimos.
- Instruye al LLM a devolver lista vacía en campos donde la convocatoria no
  aporte información clara, en lugar de rellenar por defecto.
- Devuelve un JSON con la estructura exacta:

```json
{
  "ods": [<int>, ...],
  "prioridades_geograficas": ["<str>", ...],
  "enfoques_transversales": ["<str>", ...],
  "sectores_plan_director": ["<str>", ...]
}
```

- No incluye justificación textual ni ningún campo adicional.

### Criterios de aceptación

- El archivo `opportunity_alignment.md` existe en la ubicación indicada.
- El prompt incluye la taxonomía cargada dinámicamente desde los catálogos
  YAML (no valores hardcodeados en el prompt).
- El prompt está calibrado iterativamente contra convocatorias reales, siguiendo
  el patrón ya establecido para `semantic_filter.md` (calibración por edición
  del prompt, sin cambios en código).
- La calidad del prompt no es objeto de test automático; se verifica manualmente
  contra convocatorias reales y se ajusta editando el archivo.

## R7 — Integración en el pipeline de enrichment

La extracción de alineación estratégica se integra en el pipeline de enrichment
existente, después del filtro semántico y solo para las convocatorias que ese
filtro considera relevantes.

Flujo del pipeline por convocatoria:

1. Filtro semántico (existente): decide si la convocatoria es relevante.
2. Si la convocatoria es descartada por el filtro: no se ejecuta la extracción
   de alineación estratégica; los cuatro campos quedan como `[]`.
3. Si la convocatoria pasa el filtro: se ejecuta la extracción de alineación
   estratégica; los cuatro campos se pueblan con el resultado del parser.
4. Si Ollama no está disponible (degradación silenciosa, patrón existente):
   la extracción no se ejecuta, los cuatro campos quedan como `[]`, y el
   pipeline continúa sin error.
5. Si la llamada LLM devuelve una respuesta que el parser no puede procesar
   (JSON malformado o estructura incorrecta, ver R5): se registra un log
   ERROR con el `opportunity_id` afectado, los cuatro campos quedan como `[]`,
   y el pipeline continúa sin error para esa convocatoria.

### Criterios de aceptación

- El pipeline ejecuta las dos llamadas LLM en el orden filtro → extracción,
  con la extracción condicionada al resultado positivo del filtro.
- La extracción no se ejecuta para convocatorias descartadas por el filtro.
- La ausencia de Ollama no rompe el pipeline; los campos quedan `[]`.
- Un error en la llamada LLM o en el parser no rompe el pipeline; los campos
  quedan `[]` para esa convocatoria concreta y las demás siguen procesándose.
- Los tests de integración (con Ollama mockeado) verifican los cinco escenarios
  del flujo.

## R8 — Cobertura de tests

La spec queda cubierta por tests en cuatro capas:

- **A. Unitarios del modelo** (R1): serialización, deserialización, defaults `[]`.
- **B. Unitarios de los catálogos** (R2, R3, R4): carga, estructura, no
  duplicados, coherencia con fuente oficial.
- **C. Unitarios del parser** (R5): caso feliz, valores fuera de catálogo,
  ODS fuera de rango, duplicados, JSON malformado.
- **D. Integración en el pipeline** (R7): con Ollama mockeado, los cinco
  escenarios del flujo.

### Criterios de aceptación

- Las cuatro capas están cubiertas.
- La suite completa del proyecto sigue en verde tras la implementación.
- La calidad del prompt de extracción (R6) queda **fuera** de la cobertura
  automática; se calibra manualmente.

---

## Fuera de alcance

Los siguientes puntos están relacionados pero **no** forman parte de esta spec:

- **UI de validación humana de la alineación extraída**. La extracción se hace
  automáticamente durante enrichment y el usuario ve el resultado en las tres
  vistas ya existentes (relevantes, descartadas, todas). La validación explícita
  por parte del usuario (aceptar/rechazar/corregir la alineación de cada
  convocatoria) vive en SPEC 4 (redactor), cuando el usuario arranca la
  redacción de una propuesta y necesita confirmar la alineación de la
  convocatoria elegida.
- **Fuentes nuevas de convocatorias** (decisión #28). El enrichment con
  alineación estratégica se aplica a las convocatorias que ya vienen de las
  fuentes actuales (BDNS + Tavily); ampliar fuentes es trabajo aparte.
- **Vocabulario español para queries de búsqueda** (decisión #26). Esta spec
  actúa sobre convocatorias ya encontradas, no cambia cómo se buscan.
- **Persistencia SQLite** de los catálogos editables por el usuario. Los
  catálogos son YAMLs versionados en Git, no editables desde la aplicación.
  Edición por usuario final aplazada a SPEC 5/6 (decisión #12).
