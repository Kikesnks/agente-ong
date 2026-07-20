# Design Document — alineacion-estrategica

## Overview

Diseño de la implementación de `requirements.md` (R1-R8): cuatro campos nuevos de
alineación estratégica en `Opportunity` (`ods`, `prioridades_geograficas`,
`enfoques_transversales`, `sectores_plan_director`), tres catálogos YAML nuevos con
taxonomía cerrada del Plan Director 2024-2027, un parser que valida la respuesta del LLM
extractor contra esos catálogos, un prompt de extracción nuevo
(`opportunity_alignment.md`) y su punto de enganche en el pipeline de enrichment, justo
después del filtro semántico existente y condicionado a su resultado.

## Reglas del flujo de enrichment

- La extracción **nunca** se ejecuta para convocatorias descartadas por el
  filtro. Ahorro directo de llamadas LLM.
- Ollama disponible para el filtro implica Ollama disponible para la extracción
  (misma conexión, mismo servicio). No hay caso "filtro sí, extracción no" por
  disponibilidad de servicio; sí lo hay por error puntual en la llamada.
- La ausencia de Ollama degrada silenciosamente todo el bloque LLM del
  enrichment, como ya ocurre hoy con el filtro. Convocatorias van a RELEVANTES
  sin filtrar y sin alineación extraída. Comportamiento existente extendido.
- Un error puntual en una llamada de extracción (JSON malformado, timeout, etc.)
  degrada solo esa convocatoria. Las demás siguen procesándose.

## Modelo de datos

**Corrección (2026-07-20):** esta sección asumía originalmente un modelo `Opportunity`
en `src/agente_ong/domain/opportunity.py` que no existe en el proyecto — no hay
directorio `domain/`, y el tipo más cercano, `GrantOpportunity` (`research/models.py`),
es estructuralmente distinto (cada campo es un `Claim` con verificación y fuentes) y no
se modifica desde la capa LLM (Opción B, decisión #8 de `integracion-llm`: los datos
derivados de LLM viven en tipos aditivos separados, p.ej. `EnrichedReport` en
`llm/enrichment.py`, sin tocar `research/models.py`).

Los cuatro campos se agrupan en un contenedor nuevo, independiente de
`GrantOpportunity`:

```python
# src/agente_ong/research/alignment.py
@dataclass
class AlineacionEstrategica:
    ods: list[int] = field(default_factory=list)
    prioridades_geograficas: list[str] = field(default_factory=list)
    enfoques_transversales: list[str] = field(default_factory=list)
    sectores_plan_director: list[str] = field(default_factory=list)
```

Vive en `research/` (no en `llm/`) porque el parser (R5) que lo produce también vive ahí
y no depende de LLM; `llm/` sí puede importar de `research/`, así que el extractor
(R7, tarea 6) y la integración en el pipeline (R7, tarea 7) lo consumen sin problema.

Tipos exactos y semántica:

- `ods`: lista de enteros entre 1 y 17. Sin distinción principal/secundario.
- `prioridades_geograficas`, `enfoques_transversales`, `sectores_plan_director`:
  listas de strings con nombres literales del catálogo correspondiente.
- Los cuatro campos aceptan lista vacía; lista vacía significa "no alineado"
  o "no procesado", indistinguibles a nivel de modelo (decisión aceptada).

Retrocompatibilidad:

- Una convocatoria sin alineación extraída (aún no procesada, o Ollama no
  disponible) se representa con una `AlineacionEstrategica` con las cuatro
  listas vacías (default). No requiere migración de datos existentes porque
  no se añade ningún campo a `GrantOpportunity`/`research/models.py`.
- Serialización siempre incluye los cuatro campos como listas (posiblemente
  vacías). No hay omisión de campo por lista vacía.
- Cómo se asocia exactamente cada `AlineacionEstrategica` a su convocatoria
  (p.ej. dict por URL normalizada, igual que `filter_verdicts` en
  `EnrichedReport`) es una decisión de la tarea 7, no de esta sección.

## Formato de los catálogos YAML

### `prioridades_geograficas.yaml`

```yaml
# Fuente: Plan Director de la Cooperación Española 2024-2027, sección 3.3
# NIPO 108240367
fuente:
  documento: "Plan Director de la Cooperación Española 2024-2027"
  nipo: "108240367"
  seccion: "3.3 Prioridades geográficas"

valores:
  - "América Latina y el Caribe"
  - "Norte de África"
  - "Oriente Próximo"
  - "África Subsahariana"
```

### `enfoques_transversales.yaml`

```yaml
# Fuente: Plan Director de la Cooperación Española 2024-2027, secciones 3.1.1 a 3.1.6
# NIPO 108240367
fuente:
  documento: "Plan Director de la Cooperación Española 2024-2027"
  nipo: "108240367"
  seccion: "3.1 Enfoques transversales"

valores:
  - "Enfoque de derechos humanos"
  - "Enfoque feminista y de género"
  - "Enfoque de lucha contra la pobreza y las desigualdades"
  - "Enfoque de justicia climática y sostenibilidad medioambiental"
  - "Enfoque de diversidad cultural"
  - "Enfoque de construcción de paz"
```

### `sectores_plan_director.yaml`

```yaml
# Fuente: Plan Director de la Cooperación Española 2024-2027, secciones 3.2.1, 3.2.2, 3.2.3
# NIPO 108240367
fuente:
  documento: "Plan Director de la Cooperación Española 2024-2027"
  nipo: "108240367"
  seccion: "3.2 Prioridades sectoriales"

transiciones:
  - id: "social"
    nombre: "Transición social"
    seccion_fuente: "3.2.1"
    sectores:
      - nombre: "Gobernabilidad democrática"
        ods: [16]
      - nombre: "Salud global y sistemas sanitarios"
        ods: [3]
      - nombre: "Seguridad alimentaria y lucha contra el hambre"
        ods: [2]
      - nombre: "Educación equitativa, inclusiva y de calidad y formación a lo largo de la vida"
        ods: [4]
      - nombre: "Igualdad de género y empoderamiento de todas las mujeres, niñas y adolescentes"
        ods: [3, 5, 10, 16]
      - nombre: "Cultura y desarrollo"
        ods: [11]

  - id: "ecologica"
    nombre: "Transición ecológica"
    seccion_fuente: "3.2.2"
    sectores:
      - nombre: "Lucha contra el cambio climático: adaptación y mitigación"
        ods: [13]
      - nombre: "Acceso a energías limpias"
        ods: [7]
      - nombre: "Promoción y protección de la biodiversidad"
        ods: [14, 15]
      - nombre: "Agua y saneamiento"
        ods: [6]

  - id: "economica"
    nombre: "Transición económica"
    seccion_fuente: "3.2.3"
    sectores:
      - nombre: "Desarrollo rural territorial y sistemas agroalimentarios sostenibles"
        ods: [2, 11, 14]
      - nombre: "Desarrollo económico inclusivo y sostenible"
        ods: [8, 9, 12]
      - nombre: "Digitalización para el desarrollo sostenible"
        ods: [4, 9, 16]
```

## API del catálogos_loader

Funciones públicas puras (sin estado, sin efectos secundarios más allá de leer
el archivo YAML):

```python
def cargar_prioridades_geograficas() -> list[str]:
    """Devuelve la lista literal de valores válidos."""

def cargar_enfoques_transversales() -> list[str]:
    """Devuelve la lista literal de valores válidos."""

def cargar_sectores_plan_director() -> list[str]:
    """Devuelve la lista de nombres de sector (13 valores)."""

def obtener_transicion_de_sector(sector: str) -> str:
    """Dado un nombre de sector válido, devuelve el nombre de su transición.
    Lanza ValueError si el sector no existe en el catálogo."""
```

Los catálogos se cargan en el momento de la llamada, no al importar el módulo.
Si en el futuro se detecta que el coste de I/O es notable, se añade cache LRU;
por ahora no.

## API del alignment_parser

```python
class AlignmentParseError(Exception):
    """Se lanza cuando la respuesta del LLM no es JSON parseable o no tiene
    la estructura esperada de los cuatro campos."""


def parsear_alineacion(respuesta_llm_cruda: str) -> AlineacionEstrategica:
    """Parsea la respuesta cruda del LLM extractor y devuelve los cuatro
    campos ya validados contra sus catálogos.

    - Valores fuera de catálogo se descartan con log WARNING.
    - ODS fuera del rango 1-17 se descartan con log WARNING.
    - Duplicados se colapsan preservando el orden de primera aparición.
    - JSON malformado o estructura incorrecta lanza AlignmentParseError.
    """
```

Donde `AlineacionEstrategica` es un dataclass simple con los cuatro campos
listados en R1, o un `TypedDict` equivalente (decisión de implementación menor).

## Prompt de extracción

Ubicación: `src/agente_ong/llm/prompts/opportunity_alignment.md`.

Formato general del prompt (esquema, no texto final):

1. **Rol y tarea**: rol de analista experto en cooperación española y en el
   Plan Director 2024-2027; tarea de extraer alineación estratégica de una
   convocatoria.
2. **Taxonomía**: los cuatro catálogos completos inyectados como listas de
   valores permitidos. Inyección dinámica desde los YAMLs, no hardcodeada.
3. **Instrucciones**: devolver únicamente valores literales de la taxonomía;
   lista vacía si el campo no se puede determinar con evidencia clara; no
   parafrasear; no inventar sinónimos.
4. **Formato de salida**: JSON plano con los cuatro campos exactos, sin texto
   adicional ni bloques de código.
5. **Ejemplos few-shot** (uno o dos): entrada de convocatoria realista →
   salida JSON esperada. Los ejemplos se calibran manualmente contra
   convocatorias reales.

El texto final del prompt no forma parte de esta spec: se redacta en fase de
implementación y se calibra iterativamente, siguiendo el patrón ya establecido
para `semantic_filter.md`. Los tests automáticos no evalúan la calidad del
prompt.

## API del alignment_extractor

```python
def extraer_alineacion(
    opportunity_text: str,
    llm_client: LLMClient,
) -> AlineacionEstrategica | None:
    """Ejecuta la extracción de alineación estratégica llamando al LLM.

    Devuelve la alineación parseada si la llamada y el parseo tienen éxito.
    Devuelve None si:
    - Ollama no está disponible (no se llama al LLM),
    - la llamada al LLM falla,
    - el parser lanza AlignmentParseError.

    Los tres casos se distinguen por logs (WARNING para no disponible,
    ERROR para fallo de llamada o parseo), pero el retorno es None en los tres.
    El caller convierte None a `[]` en los cuatro campos del Opportunity.
    """
```

Motivo del retorno unificado `None`: el pipeline no necesita distinguir
"Ollama caído" de "una convocatoria concreta falló", más allá de logs. El
tratamiento aguas abajo es el mismo: campos vacíos, seguir con el resto.

## Integración en `jobs.py`

**Nota (2026-07-20):** no existe `research/jobs.py`. El punto real de integración del
enrichment (`enrich_report`) es `src/agente_ong/ui/jobs.py`. El pseudocódigo siguiente es
conceptual (`Opportunity`, `filtrar_semanticamente`, `op.descartado_por`... no son nombres
reales del proyecto); el diseño concreto de esta integración —incluyendo dónde y cómo se
asocia `AlineacionEstrategica` a cada convocatoria— se resuelve en la tarea 7, no aquí.

Modificación mínima del pipeline existente:

```python
# Pseudocódigo
def enrichment_de_convocatoria(op: Opportunity, llm_client: LLMClient) -> Opportunity:
    # Paso 1 (existente): filtro semántico
    resultado_filtro = filtrar_semanticamente(op, llm_client)
    if resultado_filtro.descartada:
        op.descartado_por = resultado_filtro.razon
        return op  # Alineación queda [] por default

    # Paso 2 (nuevo): extracción de alineación
    alineacion = extraer_alineacion(op.texto_completo, llm_client)
    if alineacion is not None:
        op.ods = alineacion.ods
        op.prioridades_geograficas = alineacion.prioridades_geograficas
        op.enfoques_transversales = alineacion.enfoques_transversales
        op.sectores_plan_director = alineacion.sectores_plan_director
    # Si es None, los campos quedan [] por default. No hay branch adicional.

    return op
```

Esta modificación no toca cómo se muestran las convocatorias en las tres
vistas (RELEVANTES, DESCARTADAS, TODAS). La UI leerá los campos nuevos del
modelo cuando se decida cómo mostrarlos; esa decisión de UI vive fuera de
esta spec (ver "Impacto en UI" más abajo).

## Impacto en UI

Esta spec **no modifica la UI**. Los campos nuevos del modelo quedan
disponibles pero no se muestran en las tres vistas hasta que se decida cómo.

La razón de dejar la UI fuera es doble:

1. Mostrar cuatro listas nuevas en cada tarjeta de convocatoria puede saturar
   la vista. Requiere decisión de diseño visual aparte.
2. La utilidad plena de los campos aparece cuando se enlaza con el proyecto
   del usuario (SPEC 4), no en la vista de investigación.

Consecuencia: durante un periodo la extracción se ejecuta y persiste
información que el usuario no ve directamente. Coste aceptable: el enrichment
ya es una operación batch nocturna o por run, no interactiva.

## Impacto en tests existentes

- **Fixtures de `Opportunity`**: instancias existentes en fixtures deben
  aceptar la ausencia de los cuatro campos nuevos (via defaults). Ningún test
  existente debería fallar por esto. Si alguno falla, es señal de que la
  fixture está sobre-especificada.
- **Tests del filtro semántico y de descartados**: no se ven afectados.
  Siguen verificando el comportamiento del filtro, que no cambia.
- **Tests E2E de la UI**: no se ven afectados por defecto. Si se decide más
  tarde mostrar los campos nuevos, se añaden tests entonces.

## Riesgos y mitigaciones

**Riesgo 1: latencia del enrichment**

Añadir una segunda llamada LLM por convocatoria relevante duplica el trabajo
LLM de las convocatorias que pasan el filtro. En runs con muchas convocatorias
relevantes, el enrichment se alarga notablemente.

Mitigación: aceptada como coste conocido. Ollama es local y no cobra por token;
el usuario ve un enrichment más lento pero no más caro. Si en la práctica
resulta bloqueante, se abre una decisión posterior para paralelizar las
llamadas o mover la extracción a un job separado. No se anticipa aquí.

**Riesgo 2: el prompt de extracción invente sinónimos**

Un LLM local con instrucciones ambiguas puede devolver "género" en vez de
"Enfoque feminista y de género", perdiendo el valor.

Mitigación por diseño: el parser descarta silenciosamente valores fuera de
catálogo con log WARNING. Los logs revelan patrones de invención repetidos y
guían la iteración del prompt. Coherente con el principio del proyecto:
"filter problems are prompt problems, not code problems". Se traduce aquí a
"extraction problems are prompt problems".

**Riesgo 3: el catálogo se desalinea de la fuente oficial**

Si el Plan Director se actualiza (VII Plan Director en 2028) o se detecta un
error en la transcripción del actual, los catálogos YAML quedarán desalineados
con la nomenclatura vigente.

Mitigación: los catálogos incluyen metadatos de `fuente` (documento, NIPO,
sección). Cualquier cambio en el Plan Director exige una PR que actualice
los YAMLs y verifique los tests. La spec no automatiza la detección de
desalineación; es responsabilidad humana.

## Decisión de implementación abierta

**Reutilización del mecanismo de carga del catálogo ODS existente.**

El proyecto ya tiene `ods_catalogo.yaml` con su propio loader. Al añadir tres
catálogos más, hay dos alternativas:

- **A. Loader único genérico** que sirve para los cuatro catálogos.
  Reutilización máxima, pero el loader de ODS existente puede tener
  particularidades que no encajen.
- **B. Loaders independientes por catálogo**, cada uno adaptado a la forma
  del YAML que carga. Menos reutilización, más simplicidad inmediata.

Esta decisión se resuelve en fase de implementación al abrir el módulo y ver
el loader de ODS existente. No bloquea la spec: cualquiera de las dos
alternativas cumple los requisitos R2, R3, R4.

## Trazabilidad requirements → diseño

| Requisito | Elemento de diseño |
|---|---|
| R1 (modelo) | Sección "Modelo de datos" |
| R2 (catálogo prioridades geográficas) | `prioridades_geograficas.yaml` + `cargar_prioridades_geograficas()` |
| R3 (catálogo enfoques transversales) | `enfoques_transversales.yaml` + `cargar_enfoques_transversales()` |
| R4 (catálogo sectores) | `sectores_plan_director.yaml` + `cargar_sectores_plan_director()` + `obtener_transicion_de_sector()` |
| R5 (parser) | `alignment_parser.py`: `parsear_alineacion()` y `AlignmentParseError` |
| R6 (prompt) | `llm/prompts/opportunity_alignment.md` |
| R7 (integración) | Modificación de `jobs.py`, `alignment_extractor.py` |
| R8 (tests) | Cuatro capas: unitarios modelo, unitarios catálogos, unitarios parser, integración pipeline |
