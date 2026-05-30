# Requirements Document — Agente Investigador

## Introduction

El **agente investigador** es un módulo reutilizable y portable que busca dos tipos de
información para el sistema agente-ong:

1. **Convocatorias de subvención** (públicas y privadas) relevantes para una ONG.
2. **Proyectos aprobados de ejemplo** que sirvan como material de entrenamiento/referencia
   para redactar futuras propuestas.

Su principio rector es **calidad y veracidad por encima de velocidad**: cruza información
entre múltiples fuentes, nunca inventa datos (si no encuentra algo, lo declara y pide ayuda
al usuario), lleva registro de las fuentes ya consultadas para no repetir trabajo, e
investiga en profundidad siguiendo enlaces relevantes. Usa **Tavily** para búsqueda general,
**Firecrawl** para lectura profunda de páginas, y **fuentes oficiales** (BDNS España, TED
Europa). Descarga o copia en local los proyectos aprobados que encuentra.

El módulo se diseña como componente **independiente y portable**, de modo que pueda
reutilizarse en otros proyectos sin acoplarse al resto del sistema.

## Alignment with Product Vision

Este componente da soporte directo a las funcionalidades 1 (buscar oportunidades), 3
(aprender de ejemplos aprobados) y parcialmente 2/4 (proporcionar materia prima verificada
para redacción y recomendación) descritas en [product.md](../../steering/product.md).
Encarna el principio de producto **"calidad y verificación cruzada por encima de velocidad"**
y el principio **"el humano decide"** (cuando hay incertidumbre, pregunta en lugar de
inventar). Respeta la convención de almacenamiento `RECURSOS/ENTRENAMIENTO/` definida en
[structure.md](../../steering/structure.md) y la abstracción de fuentes de búsqueda de
[tech.md](../../steering/tech.md).

## Requirements

### Requirement 1 — Búsqueda de convocatorias de subvención

**User Story:** Como técnico de una ONG, quiero que el agente busque convocatorias de
subvención públicas y privadas relevantes para mi organización, para descubrir
oportunidades de financiación sin rastrear manualmente múltiples portales.

#### Acceptance Criteria

1. WHEN el usuario solicita buscar convocatorias con uno o más criterios (temática, ámbito
   geográfico, importe, plazo) THEN el sistema SHALL consultar Tavily para búsqueda general
   y las fuentes oficiales BDNS (España) y TED (UE) cuando apliquen al ámbito.
2. WHEN el agente identifica una convocatoria candidata THEN el sistema SHALL extraer al
   menos: título, organismo convocante, importe/cuantía, plazo de presentación, ámbito y
   URL de origen.
3. IF un dato obligatorio de una convocatoria no puede confirmarse en la fuente THEN el
   sistema SHALL marcar ese campo como "no encontrado" en lugar de rellenarlo con una
   suposición.
4. WHEN se devuelve un conjunto de convocatorias THEN el sistema SHALL incluir la URL de
   fuente verificable de cada una.

### Requirement 2 — Búsqueda y captura de proyectos aprobados de ejemplo

**User Story:** Como sistema de redacción, quiero que el agente localice y guarde en local
proyectos de subvención ya aprobados, para disponer de material de entrenamiento y
referencia de alta calidad.

#### Acceptance Criteria

1. WHEN el usuario o el sistema solicita material de entrenamiento sobre una temática THEN
   el sistema SHALL buscar proyectos/propuestas aprobadas o plantillas oficiales relevantes.
2. WHEN se encuentra un documento de proyecto aprobado descargable THEN el sistema SHALL
   descargarlo en `RECURSOS/ENTRENAMIENTO/`.
3. IF el documento no es descargable directamente THEN el sistema SHALL guardar una copia
   local del contenido (texto extraído vía Firecrawl) junto con la URL de origen.
4. WHEN se guarda un recurso de entrenamiento THEN el sistema SHALL registrar metadatos
   mínimos (URL de origen, fecha de captura, temática/etiquetas) asociados al archivo.
5. IF un recurso ya fue capturado previamente (misma URL) THEN el sistema SHALL evitar
   descargarlo de nuevo.

### Requirement 3 — Veracidad y no alucinación

**User Story:** Como usuario que tomará decisiones de financiación, quiero que el agente
nunca invente datos, para poder confiar en que toda la información tiene una fuente real.

#### Acceptance Criteria

1. WHEN el agente no encuentra información solicitada tras agotar las fuentes disponibles
   THEN el sistema SHALL declararlo explícitamente y pedir ayuda/orientación al usuario.
2. WHEN el agente presenta cualquier afirmación factual (importe, plazo, requisito) THEN el
   sistema SHALL asociar dicha afirmación a una URL/fuente concreta.
3. IF dos fuentes presentan datos contradictorios sobre el mismo hecho THEN el sistema SHALL
   señalar la discrepancia y las fuentes implicadas en lugar de elegir una en silencio.
4. WHEN se requiere un dato crítico y solo existe una única fuente sin corroborar THEN el
   sistema SHALL distinguir entre dos estados y etiquetarlo en consecuencia: "fuente oficial,
   no cruzada" (aceptable, cuando procede de una fuente oficial — ver Requirement 4) o "no
   verificado de forma cruzada" (estado preocupante, cuando procede de una fuente no oficial).

### Requirement 4 — Verificación cruzada entre fuentes

**User Story:** Como usuario, quiero que el agente contraste la información en varias
fuentes antes de darla por buena, para maximizar la fiabilidad de los resultados.

#### Acceptance Criteria

1. WHEN se confirma un dato clave de una convocatoria (importe, plazo, beneficiarios) THEN
   el sistema SHALL intentar corroborarlo en al menos una fuente adicional cuando exista.
2. WHEN un dato queda corroborado por dos o más fuentes THEN el sistema SHALL marcarlo como
   "verificado" e indicar las fuentes.
3. IF el agente debe elegir entre velocidad y una verificación adicional disponible THEN el
   sistema SHALL priorizar la verificación.
4. WHEN un dato proviene de una fuente oficial (BDNS, TED, boletín o diario oficial) THEN el
   sistema SHALL considerarlo fiable sin exigir una segunda fuente, PERO SHALL marcarlo
   explícitamente como "fuente oficial, no cruzada", indicando la fuente oficial concreta,
   para que el usuario conozca el motivo por el que no se ha verificado de forma cruzada.

### Requirement 5 — Registro de fuentes consultadas (sin repetición)

**User Story:** Como agente eficiente, quiero llevar registro de las fuentes ya
consultadas, para no repetir consultas ni reprocesar las mismas páginas dentro de una
investigación.

#### Acceptance Criteria

1. WHEN el agente consulta una URL o lanza una consulta de búsqueda THEN el sistema SHALL
   registrarla en un registro de fuentes consultadas de la investigación en curso.
2. IF una URL ya figura en el registro como consultada THEN el sistema SHALL omitir volver
   a procesarla salvo petición explícita de refresco.
3. WHEN finaliza una investigación THEN el sistema SHALL poder devolver la lista de fuentes
   consultadas y su resultado (útil / sin valor / error).

### Requirement 6 — Investigación en profundidad (seguir enlaces)

**User Story:** Como usuario, quiero que el agente profundice siguiendo enlaces relevantes,
para no quedarse en la superficie de los resultados de búsqueda.

#### Acceptance Criteria

1. WHEN una página consultada contiene enlaces relevantes para la consulta (p.ej. ficha de
   convocatoria, bases reguladoras, anexos) THEN el sistema SHALL poder seguir esos enlaces
   con Firecrawl hasta una profundidad configurable.
2. WHEN se sigue un enlace THEN el sistema SHALL aplicar el mismo registro de fuentes para
   evitar ciclos y repeticiones.
3. IF la profundidad o el número de páginas configurado se alcanza THEN el sistema SHALL
   detener la expansión y reportar lo encontrado hasta ese punto.

### Requirement 7 — Módulo independiente y portable

**User Story:** Como desarrollador, quiero que el investigador sea un módulo desacoplado,
para poder reutilizarlo en otros proyectos sin arrastrar dependencias del resto del sistema.

#### Acceptance Criteria

1. WHEN se integra el módulo en otro proyecto THEN el sistema SHALL exponer una interfaz
   pública clara (entrada: criterios de búsqueda; salida: resultados estructurados con
   fuentes) sin depender de la UI ni de otros agentes del sistema.
2. WHEN el módulo necesita claves de API o rutas de almacenamiento THEN el sistema SHALL
   obtenerlas por configuración inyectada (variables de entorno / parámetros), nunca
   hardcodeadas.
3. WHEN se sustituye un proveedor de búsqueda THEN el sistema SHALL permitirlo a través de
   la abstracción de fuentes sin modificar la lógica del agente.

## Non-Functional Requirements

### Performance
- La prioridad explícita es **calidad sobre velocidad**: es aceptable que una investigación
  tarde más a cambio de mayor verificación. Aun así, debe respetar límites configurables de
  profundidad de enlaces y número máximo de páginas/consultas por investigación para evitar
  bucles o costes descontrolados.
- Las llamadas a APIs externas (Tavily, Firecrawl, BDNS, TED) deben gestionar rate limits y
  reintentos con backoff.

### Security
- Las claves de API se gestionan exclusivamente por variables de entorno / configuración
  inyectada; nunca se almacenan en el repositorio ni en los resultados.
- Los documentos descargados se guardan únicamente bajo `RECURSOS/ENTRENAMIENTO/`,
  validando rutas para evitar escritura fuera de ese directorio (path traversal).

### Reliability
- El fallo de una fuente (timeout, error HTTP, sin resultados) no debe abortar toda la
  investigación: el agente continúa con las demás fuentes y reporta cuáles fallaron.
- Toda afirmación factual devuelta es trazable a su fuente (sin resultados sin procedencia).

### Usability
- Cuando falte información, el mensaje al usuario debe ser claro sobre **qué** falta y **qué
  ayuda** se necesita (p.ej. una URL, una palabra clave, acceso a un portal).
- Los resultados se devuelven en una estructura consistente y legible, con el estado de
  verificación de cada dato (verificado / fuente oficial no cruzada / no verificado de forma
  cruzada / no encontrado).
