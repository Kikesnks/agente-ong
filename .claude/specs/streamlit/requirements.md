# Requirements Document — Interfaz Streamlit

## Introduction

La **interfaz Streamlit** es la capa de aplicación web de agente-ong: el punto de entrada
con el que las ONGs (usuarios **sin perfil técnico**) interactúan con el sistema. Es la cara
visible que orquesta los módulos ya existentes —empezando por el **agente investigador**
(fachada `Investigador.run(request) -> ResearchReport`)— y los presenta de forma sencilla:
crear y gestionar proyectos, subir documentación de la ONG, lanzar búsquedas de convocatorias
y consultar los resultados con su trazabilidad y estado de verificación.

Esta primera spec de UI se centra en tres decisiones de producto ya tomadas:

1. **Investigación asíncrona** — el usuario lanza una investigación y la app sigue siendo
   usable mientras trabaja en segundo plano (Requirement 2).
2. **Múltiples proyectos por sesión** — el usuario gestiona varios proyectos/investigaciones
   simultáneamente sin mezclar su contexto (Requirement 1).
3. **Subida de documentos de contexto** — el usuario sube documentos de su ONG para
   contextualizar el trabajo; se guardan en `RECURSOS/[nombre_proyecto]/` (Requirement 3).

Sobre esa base, la spec añade controles para afinar la investigación desde la UI: nivel de
profundidad (R8), fuente directa y activación de fuentes (R9), filtro temporal por año (R10),
y resultados ordenados y filtrables (R11); más el modelo de datos de proyectos y su gestión
(R12, que concreta R1/R6).

Nota técnica: Streamlit reejecuta el script en cada interacción y es de un solo hilo por
sesión; el cumplimiento del requisito de asincronía (no bloquear la UI) exige un mecanismo
de trabajo en segundo plano + sondeo de estado que se concretará en la fase de diseño.

## Alignment with Product Vision

Esta interfaz materializa las **"Interacciones tipo (interfaz web)"** descritas en
[product.md](../../steering/product.md): subir recursos por proyecto, pedir acciones en
lenguaje sencillo, visualizar respuestas de la IA y, más adelante, descargar entregables.
Da soporte directo a la funcionalidad 1 (búsqueda de oportunidades) exponiéndola al usuario
final, y encarna el principio **"Accesible para no técnicos"** (la complejidad multi-agente
queda oculta tras una UI sencilla) y **"El humano decide"** (la IA propone; la persona
revisa). Respeta la convención de almacenamiento `RECURSOS/[nombre_proyecto]/` de
[structure.md](../../steering/structure.md), usa **Streamlit** como capa de UI y **SQLite**
como persistencia del producto según [tech.md](../../steering/tech.md), y reutiliza el módulo
**investigador** ya implementado sin acoplarse a su interior (Requirement 7 de esa spec).

## Requirements

### Requirement 1 — Gestión de múltiples proyectos por sesión

> Decisión de producto 2: el usuario gestiona múltiples proyectos/investigaciones por sesión.

**User Story:** Como técnico de una ONG, quiero gestionar varios proyectos en la misma
sesión, para trabajar en paralelo en distintas convocatorias sin perder el contexto de cada
uno.

#### Acceptance Criteria

1. WHEN el usuario abre la interfaz THEN el sistema SHALL mostrar la lista de proyectos
   existentes (recuperados de la persistencia) y ofrecer crear uno nuevo indicando su nombre.
2. WHEN el usuario crea un proyecto con un nombre válido THEN el sistema SHALL crear (si no
   existe) la carpeta `RECURSOS/[nombre_proyecto]/` y registrar el proyecto en SQLite.
3. WHEN el usuario selecciona un proyecto THEN el sistema SHALL mostrar su estado, sus
   documentos subidos y los resultados de sus investigaciones, sin mezclarlos con los de
   otros proyectos.
4. IF el nombre de proyecto introducido ya existe o contiene caracteres no válidos para una
   ruta THEN el sistema SHALL rechazarlo con un mensaje claro y no crear carpetas.
5. WHEN el usuario cambia de un proyecto a otro THEN el sistema SHALL conservar el estado del
   proyecto anterior, incluidas las investigaciones que tenga en curso.

### Requirement 2 — Lanzamiento de investigación asíncrona (no bloqueante)

> Decisión de producto 1: el usuario lanza la investigación y la app trabaja en segundo plano
> sin bloquearlo.

**User Story:** Como usuario, quiero lanzar una investigación de convocatorias y seguir
usando la app mientras trabaja en segundo plano, para no quedarme bloqueado esperando.

#### Acceptance Criteria

1. WHEN el usuario lanza una investigación para un proyecto THEN el sistema SHALL iniciarla
   en segundo plano y devolver de inmediato el control de la interfaz al usuario.
2. WHILE una investigación está en curso THEN el sistema SHALL mostrar su estado "en
   progreso" y permitir al usuario navegar, consultar otros proyectos o lanzar otras acciones.
3. WHEN una investigación en segundo plano finaliza THEN el sistema SHALL actualizar el
   proyecto con el informe resultante e indicar de forma visible que ha terminado.
4. IF una investigación en segundo plano falla THEN el sistema SHALL reflejar el error en el
   proyecto sin caer la aplicación ni afectar a los demás proyectos.
5. WHEN el usuario tiene varias investigaciones lanzadas a la vez THEN el sistema SHALL
   gestionarlas de forma independiente y mostrar el estado de cada una.

### Requirement 3 — Subida de documentos de contexto de la ONG

> Decisión de producto 3: el usuario sube documentos de su ONG para contextualizar; van a
> `RECURSOS/[nombre_proyecto]/`.

**User Story:** Como técnico de una ONG, quiero subir documentos de mi organización (memorias,
proyectos previos, datos) en un proyecto, para que la IA contextualice su trabajo según mi
entidad.

#### Acceptance Criteria

1. WHEN el usuario sube uno o más documentos dentro de un proyecto THEN el sistema SHALL
   guardarlos en `RECURSOS/[nombre_proyecto]/`.
2. WHEN se guarda un documento subido THEN el sistema SHALL validar la ruta de destino para
   impedir escritura fuera de `RECURSOS/[nombre_proyecto]/` (path traversal) y conservar su
   nombre de origen.
3. IF el archivo supera un tamaño máximo configurable o su tipo no está permitido THEN el
   sistema SHALL rechazarlo con un mensaje claro y no guardarlo.
4. WHEN existen documentos subidos en un proyecto THEN el sistema SHALL listarlos en la vista
   del proyecto y permitir eliminarlos.
5. IF se sube un documento con el mismo nombre que uno ya existente en el proyecto THEN el
   sistema SHALL evitar sobrescribirlo de forma silenciosa (renombrar o pedir confirmación).

### Requirement 4 — Visualización de resultados con trazabilidad y verificación

**User Story:** Como usuario que decide sobre financiación, quiero ver los resultados de cada
investigación con su fuente y su estado de verificación, para confiar en la información antes
de actuar.

#### Acceptance Criteria

1. WHEN se muestra el informe de una investigación THEN el sistema SHALL presentar cada
   convocatoria con sus campos (título, organismo, importe, plazo, ámbito, URL) y su URL de
   fuente verificable.
2. WHEN se muestra un dato THEN el sistema SHALL indicar su estado de verificación
   (verificado / fuente oficial no cruzada / no verificado de forma cruzada / no encontrado).
3. WHEN una investigación declara datos no resueltos o pide ayuda THEN el sistema SHALL
   mostrar claramente qué falta y qué ayuda se necesita.
4. IF una o más fuentes han fallado durante la investigación THEN el sistema SHALL indicarlo
   sin ocultar el resto de resultados.

### Requirement 5 — Interacción accesible para usuarios no técnicos

**User Story:** Como persona sin perfil técnico, quiero pedir acciones de forma sencilla y
entender lo que ocurre, para usar la herramienta sin conocimientos técnicos.

#### Acceptance Criteria

1. WHEN el usuario inicia una investigación THEN el sistema SHALL ofrecer una entrada sencilla
   (temática, ámbito, importe, plazo) sin exigir conocimientos técnicos ni editar
   configuración.
2. WHEN la app realiza una operación de larga duración THEN el sistema SHALL mostrar
   retroalimentación de progreso comprensible.
3. WHEN ocurre un error THEN el sistema SHALL mostrar un mensaje claro y orientado a la
   acción, sin exponer trazas técnicas crudas.

### Requirement 6 — Persistencia y recall entre sesiones

**User Story:** Como usuario, quiero que la app recuerde mis proyectos, sus documentos y sus
resultados entre sesiones, para retomar el trabajo donde lo dejé.

#### Acceptance Criteria

1. WHEN el usuario reabre la app THEN el sistema SHALL recuperar de SQLite los proyectos
   existentes, su estado y sus investigaciones previas.
2. WHEN cambia el estado de un proyecto o finaliza una investigación THEN el sistema SHALL
   persistir el cambio en SQLite.
3. WHEN el usuario consulta un proyecto previo THEN el sistema SHALL mostrar sus documentos
   (de `RECURSOS/[nombre_proyecto]/`) y los informes guardados de sus investigaciones.

### Requirement 7 — Descarga del resultado de la investigación

**User Story:** Como usuario, quiero descargar el resultado de una investigación, para
conservarlo o compartirlo fuera de la app.

#### Acceptance Criteria

1. WHEN una investigación ha finalizado con resultados THEN el sistema SHALL permitir
   descargar su informe en un formato legible (incluyendo, por cada dato, su fuente y estado
   de verificación).
2. IF una investigación no ha producido resultados THEN el sistema SHALL deshabilitar o
   indicar la no disponibilidad de la descarga, sin generar un archivo vacío engañoso.

> Nota de alcance: la exportación enriquecida a PDF/DOCX/PPTX de los **entregables** de
> propuesta (no de este informe) se aborda en su propia spec de exportación; aquí solo se
> cubre la descarga del informe de investigación.

### Requirement 8 — Control del nivel de profundidad de la búsqueda

**User Story:** Como usuario, quiero elegir cuánto se esfuerza la investigación
(rápida / normal / exhaustiva), para equilibrar coste y tiempo frente a exhaustividad según
el caso.

#### Acceptance Criteria

1. WHEN el usuario lanza una investigación THEN el sistema SHALL ofrecer un selector de nivel
   con tres opciones: "rápida", "normal" y "exhaustiva".
2. WHEN el usuario elige un nivel THEN el sistema SHALL mapearlo a los parámetros `max_depth`
   y `max_pages` de la investigación (override de `ResearchConfig` vía `ResearchRequest`),
   con valores crecientes de rápida → normal → exhaustiva.
3. IF el usuario no elige nivel THEN el sistema SHALL aplicar "normal" como valor por defecto.
4. WHEN se muestra cada nivel THEN el sistema SHALL describir en lenguaje sencillo su efecto
   (p.ej. "exhaustiva: más fuentes y enlaces, tarda más"), sin exponer los números internos.

### Requirement 9 — Fuente directa y activación de fuentes

**User Story:** Como usuario con conocimiento del terreno, quiero indicar una URL concreta y/o
elegir qué fuentes se usan, para dirigir la investigación cuando ya sé dónde mirar o quiero
acotar el coste.

#### Acceptance Criteria

1. WHEN el usuario indica una o más URLs concretas THEN el sistema SHALL hacer que el
   investigador las lea directamente en profundidad con Firecrawl, integrando su contenido en
   el informe con su trazabilidad habitual.
2. WHEN el usuario abre las opciones de fuentes THEN el sistema SHALL permitir activar o
   desactivar individualmente cada fuente disponible (Tavily, BDNS, TED, Firecrawl).
3. WHEN el usuario lanza la investigación con un subconjunto de fuentes THEN el sistema SHALL
   usar únicamente las fuentes activadas y reflejar en el informe cuáles se consultaron.
4. IF el usuario desactiva todas las fuentes de búsqueda pero indica al menos una URL directa
   THEN el sistema SHALL ejecutar igualmente la lectura directa de esas URLs.
5. IF no hay ninguna fuente activada ni URL directa THEN el sistema SHALL impedir el
   lanzamiento con un mensaje claro.

### Requirement 10 — Filtro temporal (año mínimo)

**User Story:** Como usuario, quiero descartar convocatorias antiguas indicando un año mínimo,
para centrarme en oportunidades vigentes.

#### Acceptance Criteria

1. WHEN el usuario indica un año mínimo THEN el sistema SHALL aplicarlo como filtro `min_year`
   a las fuentes oficiales que lo soportan (TED, ya existente; y BDNS, extendiendo el filtro).
2. WHEN se extiende `min_year` a BDNS THEN el sistema SHALL filtrar las convocatorias por su
   fecha de forma coherente con el comportamiento ya definido en TED.
3. IF el usuario no indica año mínimo THEN el sistema SHALL no aplicar filtro temporal (sin
   cambios respecto al comportamiento actual).
4. WHEN una fuente no soporta filtro temporal (p.ej. Tavily) THEN el sistema SHALL ignorar el
   filtro para esa fuente sin provocar error.

### Requirement 11 — Resultados ordenados y filtrables

**User Story:** Como usuario, quiero que las convocatorias aparezcan ordenadas por fiabilidad
y poder filtrarlas, para encontrar antes las oportunidades sólidas y relevantes.

#### Acceptance Criteria

1. WHEN se presenta la lista de convocatorias THEN el sistema SHALL ordenarla por estado de
   verificación, en este orden: VERIFIED, OFFICIAL_UNCROSSED, UNCROSSED_UNVERIFIED,
   CONFLICTING, NOT_FOUND.
2. WHEN el usuario aplica un filtro por estado de verificación THEN el sistema SHALL mostrar
   solo las convocatorias cuyo estado coincide con la selección.
3. WHEN el usuario aplica un filtro por fecha o por importe THEN el sistema SHALL mostrar solo
   las convocatorias que cumplen el criterio, tratando con claridad los datos "no encontrado"
   (p.ej. excluidos o agrupados aparte, nunca como valor cero engañoso).
4. WHEN el usuario combina varios filtros THEN el sistema SHALL aplicarlos de forma conjunta
   (AND) y mantener el orden por estado de verificación dentro del resultado.

### Requirement 12 — Modelo y gestión de proyectos

> Refina y concreta el Requirement 1 (gestión de proyectos) y el Requirement 6 (persistencia):
> introduce el modelo de datos `Project` y su tabla en SQLite.

**User Story:** Como técnico de una ONG, quiero una lista de proyectos con sus datos y un
formulario para crearlos, y que cada investigación quede asociada a un proyecto, para
organizar mi trabajo por iniciativa.

#### Acceptance Criteria

1. WHEN el sistema gestiona proyectos THEN el sistema SHALL definir un modelo `Project` con al
   menos: nombre, fecha de creación, objetivo y términos de búsqueda asociados.
2. WHEN se crea o actualiza un proyecto THEN el sistema SHALL persistirlo en una tabla nueva
   de SQLite (p.ej. `projects`), separada de las tablas existentes del investigador.
3. WHEN el usuario abre la app THEN el sistema SHALL mostrar la lista de proyectos creados con
   sus datos (nombre, fecha, objetivo).
4. WHEN el usuario crea un proyecto THEN el sistema SHALL ofrecer un formulario que capture
   nombre, objetivo y términos de búsqueda, validando los campos obligatorios.
5. WHEN el usuario lanza una investigación THEN el sistema SHALL asociarla a un proyecto
   concreto, de modo que sus resultados queden vinculados a ese proyecto.
6. WHEN se asocian las investigaciones a proyectos THEN el sistema SHALL poder recuperar, por
   proyecto, sus investigaciones y resultados previos.

## Non-Functional Requirements

### Performance
- La interfaz SHALL permanecer responsiva mientras haya investigaciones en segundo plano:
  ninguna operación larga bloquea el hilo de la UI (Requirement 2). El estado se refresca por
  sondeo sin congelar la interacción.
- El arranque de la app y la carga de la lista de proyectos desde SQLite deben ser ágiles
  (lectura de metadatos, no del contenido completo de los recursos).

### Security
- Los documentos subidos se guardan **exclusivamente** bajo `RECURSOS/[nombre_proyecto]/`,
  validando y normalizando rutas para impedir path traversal (escritura fuera del directorio).
- La subida valida tipo y tamaño máximo de archivo (límites configurables) antes de persistir.
- Sin secretos en el repo: las claves de API se obtienen por variables de entorno / `.env`;
  la UI nunca las muestra ni las solicita en claro.

### Reliability
- El fallo de una investigación en segundo plano, de una fuente o de una subida no debe tumbar
  la aplicación ni afectar a otros proyectos: el error se aísla y se reporta en su proyecto.
- El estado de proyectos e investigaciones se persiste de forma consistente en SQLite para
  sobrevivir a reinicios de la app (recuperación al reabrir — Requirement 6).

### Usability
- Lenguaje claro y orientado a no técnicos; retroalimentación de progreso visible en
  operaciones largas; mensajes de error accionables (Requirement 5).
- El estado de verificación de cada dato (verificado / fuente oficial no cruzada / no
  verificado de forma cruzada / no encontrado) se presenta de forma comprensible para el
  usuario final (Requirement 4).
