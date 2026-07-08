# Spec investigador-v2 — requirements.md (APROBADO por Kike el 12-06-2026)

## Reaperturas — 05-07-2026 (R24) y 08-07-2026 (R25)

### Reapertura R24 — 05-07-2026

**Motivo:** ampliar el vocabulario de búsqueda del investigador (R16) con
términos alineados con los Objetivos de Desarrollo Sostenible (ODS) y la
Agenda 2030, para captar convocatorias anunciadas con lenguaje de cooperación
internacional.

**Origen del pendiente:** `Contexto_para_mi/pendientes_ods_investigador.md`
sección 1.

**Alcance de la reapertura:** solo retoques al vocabulario (R24). Fuentes
nuevas y campos ODS en el modelo `Opportunity` quedan fuera (ver "Fuera de
alcance").

**Fecha de cierre:** 05-07-2026. Reapertura completada: T20-T23 implementadas,
315 tests en verde (309 previos + 6 nuevos).

### Reapertura R25 — 08-07-2026

**Motivo:** hallazgo abierto de la prueba humana del 05-07-2026 (desaparición
de resultados Tavily por saturación del pool de hits con las 5 queries ODS
genéricas fijas de R24 — ver decisión pendiente #13 en
`Contexto_para_mi/decisiones_pendientes.md`) y problema de fondo: las queries
ODS fijas no reflejan la intención real del usuario en cada búsqueda.

**Alcance de la reapertura:** sustituir el vocabulario ODS fijo de R24 por
selección explícita del usuario desde la UI (R25). Persistencia de ODS en el
modelo `Opportunity` queda fuera (ver "Fuera de alcance", R25.4).

**Fecha de cierre:** pendiente.

*Fecha: 12-06-2026. Origen: diagnóstico de los informes de producción del 12-06-2026
(búsqueda rápida, 104 resultados; búsqueda exhaustiva, 108 resultados; 0 convocatorias
útiles en ambos).*

## Introducción

La primera prueba en producción reveló que el investigador devuelve documentos
relacionados con la temática (estudios, noticias, páginas de ONGs, licitaciones) pero no
convocatorias de subvención abiertas. Esta spec corrige los defectos diagnosticados sin
depender de validación externa. El principio rector se mantiene: calidad y verificación
cruzada por encima de velocidad; nunca inventar datos.

Alcance: solo `src/agente_ong/research/`. Cambios retrocompatibles donde sea posible.
Fuera de alcance: filtrado semántico con LLM ("¿es esto una convocatoria abierta?"),
que pertenece a la SPEC 2+ — pero esta spec deja el terreno preparado (R20).

---

## R14 — La verificación cruzada no cuenta fuentes duplicadas

**Evidencia:** resultados marcados "Verificado (2+ fuentes)" cuyas fuentes son la misma
URL repetida 2-3 veces. Corrompe la propuesta de valor central del producto.

Criterios de aceptación:
- 14.1 Dos referencias con la misma `source_url_norm` cuentan como UNA fuente a efectos
  de verificación.
- 14.2 El estado VERIFIED exige 2+ fuentes con `source_url_norm` DISTINTAS (y se mantiene
  la regla existente sobre oficialidad).
- 14.3 La lista de fuentes mostrada en el informe no contiene URLs repetidas.
- 14.4 Test de regresión con el caso real: misma URL tres veces → "Sin verificar
  (1 fuente)", nunca "Verificado".

## R15 — TED queda excluido del modo subvenciones

**Evidencia:** el 100% de los resultados TED son licitaciones (compra de vehículos,
mantenimiento de edificios, desarrollo de software). TED publica contratación pública,
no subvenciones; el match se produce incluso contra el NOMBRE del organismo
("Consejería de... Soberanía Alimentaria").

Criterios de aceptación:
- 15.1 En `mode="calls"` (subvenciones), TedSource no se consulta.
- 15.2 El código de TedSource NO se elimina: queda disponible para un futuro modo
  "licitaciones" (decisión de producto registrada, sin spec).
- 15.3 La UI deja de ofrecer TED como fuente activable en investigaciones de
  subvenciones (cambio mínimo en `_SOURCE_LABELS`/app.py, sin rediseño).
- 15.4 La decisión queda documentada en design.md con su evidencia.

## R16 — Las queries a Tavily usan vocabulario de convocatoria

**Evidencia:** términos como "cooperación internacional + seguridad alimentaria"
devuelven proyectos YA financiados, estudios y noticias — la ejecución de fondos,
no la oferta.

Criterios de aceptación:
- 16.1 Las queries enviadas a Tavily combinan los términos del usuario con vocabulario
  de oferta de financiación (p.ej. "convocatoria", "subvención", "bases reguladoras",
  "plazo de presentación" — lista exacta a fijar en design.md, configurable).
- 16.2 Los términos del usuario no se alteran en BDNS (su corpus ya es solo subvenciones).
- 16.3 El `search_context` del proyecto se sigue aplicando (no se sustituye, se complementa).
- 16.4 Test: la query construida para Tavily contiene al menos un término de vocabulario
  de convocatoria.
- 16.5 (Decisión P1, opción b) Tavily pasa a fuente secundaria para subvenciones: sus
  resultados se clasifican como máximo `documento_informativo` (R20) salvo heurística
  fuerte de convocatoria. Se mantiene activable: sus resultados son material valioso
  como contexto y como ejemplos de proyectos redactados para el futuro RAG/redactor
  (SPEC 3/4). La razón queda documentada en design.md.

## R17 — Filtro temporal también en Tavily

**Evidencia:** documento de 2009 entre los resultados ("Crisis y pobreza rural...
Noviembre 2009"). `min_year` solo se aplicaba a BDNS y TED.

Criterios de aceptación:
- 17.1 Los resultados de Tavily con fecha identificable anterior a `min_year` se descartan.
- 17.2 Resultados sin fecha identificable NO se descartan (no inventar antigüedad,
  coherente con R10.3) pero se marcan (p.ej. `date_unknown`) para que el informe lo refleje.
- 17.3 Si la API de Tavily ofrece parámetros de recencia, usarlos además del filtro en
  cliente (verificar en design.md).

## R18 — Limpieza del contenido extraído

**Evidencia:** campos del informe con menús de navegación, avisos de cookies, selectores
de idioma ("Skip to content", "ES / CAT", "Nuestra web utiliza cookies...").

Criterios de aceptación:
- 18.1 El texto que llega a los campos del informe excluye elementos de plantilla web:
  navegación, cookies, footers, formularios de suscripción (heurísticas a definir en
  design.md; perfección no exigida, mejora drástica sí).
- 18.2 Los snippets por campo tienen longitud máxima configurable (los informes actuales
  de 1.900+ líneas son inutilizables).
- 18.3 El campo "Organismo" no puede contener más de N caracteres (hoy contiene páginas
  enteras).

## R19 — BDNS con llamada al detalle: importe y plazo

**Evidencia:** 104/104 y 108/108 resultados sin importe ni plazo — los dos datos que una
ONG mira primero. En BDNS viven en el endpoint de detalle
(`/convocatorias?numConv=...` → `presupuestoTotal`), ya investigado.
*(Promovido desde v1.1 por el diagnóstico: sin estos datos el informe no es accionable.)*

Criterios de aceptación:
- 19.1 Para cada convocatoria BDNS que supere los filtros, una llamada al detalle
  recupera importe y plazo cuando existan.
- 19.2 El filtro `min_year` se aplica ANTES de las llamadas al detalle (no gastar
  llamadas en descartes — nota ya registrada en el roadmap).
- 19.3 Límite configurable de llamadas al detalle por investigación (control de coste/tiempo).
- 19.4 Si el detalle no aporta el dato, se mantiene "No encontrado" — nunca inventar.

## R20 — Preparación para el filtrado semántico (SPEC 2+)

Los resultados incorporan la información que el futuro filtro LLM necesitará, sin
implementar el filtro.

Criterios de aceptación:
- 20.1 Campo `result_type` en los resultados con valores provisionales asignables por
  heurística: `convocatoria_probable`, `documento_informativo`, `desconocido`
  (heurística simple en design.md: presencia de plazo/bases/importe en el texto, dominio
  oficial, etc.).
- 20.2 El informe agrupa o señala los `documento_informativo` por separado (el usuario
  distingue de un vistazo lo accionable).
- 20.3 El campo es opcional/retrocompatible (default `desconocido`).

## R21 — Re-validación con casos reales

Criterios de aceptación:
- 21.1 Se re-ejecutan las DOS búsquedas de los informes del 12-06-2026 (mismos términos,
  mismo contexto) y se comparan: % de resultados tipo convocatoria, presencia de
  importe/plazo en resultados BDNS, ausencia de duplicados en verificación, ausencia de
  licitaciones TED, ausencia de documentos pre-min_year con fecha conocida.
- 21.2 El antes/después queda documentado (sirve además como material de portafolio).
- 21.3 La validación de criterio fino ("¿le sirve a una ONG real?") queda explícitamente
  pendiente de testers expertos — fuera de esta spec.

---

## R22 — Informe en dos vistas: resumido y detallado (decisión P2)

El informe actual (1.900+ líneas) es inutilizable para el usuario final pero valioso
para análisis y diagnóstico.

Criterios de aceptación:
- 22.1 Vista/descarga RESUMIDA: por convocatoria, solo título, organismo, importe,
  plazo, URL y estado de verificación — pocas líneas por resultado.
- 22.2 Vista/descarga DETALLADA: el contenido completo actual, con la limpieza de R18.
- 22.3 La UI muestra la resumida por defecto; ambas son descargables.
- 22.4 Las dos vistas se generan del mismo informe persistido (sin segunda investigación).

---

## R23 — Lectura profunda sin dependencia de créditos

**Contexto:** Firecrawl agotó sus créditos en la primera prueba real (757 créditos en dos
búsquedas) y además falló en producción con algunos sitios. La fase de pruebas con testers
requiere búsquedas ilimitadas sin coste. El detalle BDNS (R19) ya cubre importe/plazo, por
lo que la lectura profunda queda relegada a material complementario que no justifica coste
por llamada.

Criterios de aceptación:
- 23.1 Existirá un adapter de lectura propio (HttpReaderSource o nombre equivalente)
  basado en httpx + trafilatura, implementando el mismo puerto de lectura que Firecrawl,
  sin dependencias de pago. La extracción del texto principal descarta plantilla web
  (complementa, no sustituye, la limpieza de R18).
- 23.2 El lector propio será la opción POR DEFECTO para la lectura profunda. Firecrawl
  pasa a fallback opcional: solo se invoca si el lector propio falla en una URL (error de
  red tras reintentos o extracción vacía) Y hay créditos configurados.
- 23.3 En modo "calls", la lectura profunda solo se aplicará a hits con result_type =
  "convocatoria_probable" (usa la clasificación de R20), independientemente del lector.
  Los documento_informativo y desconocido no consumen lectura profunda. En modo
  "training" este gating NO aplica: todos los hits siembran la lectura profunda, porque
  el material informativo y desconocido es justo lo que se busca capturar como ejemplo
  de entrenamiento (coherente con la reserva de esos tipos en R20).
- 23.4 Límites configurables en ResearchConfig (+ env): reader_max_pages (máximo de
  páginas leídas en profundidad por búsqueda, default a proponer en design) y
  firecrawl_max_calls (máximo de llamadas al fallback por búsqueda, default 0 = fallback
  desactivado). Default 0 garantiza coste cero salvo activación explícita.
- 23.5 El fallo de lectura (propio y fallback) no descarta el hit: conserva sus datos de
  búsqueda y el informe refleja que no se pudo leer en profundidad (coherente con 19.4 —
  nunca inventar, siempre trazable).
- 23.6 Los tests usarán fakes de cliente HTTP (patrón _FakeHttp); habrá UNA verificación
  en vivo del lector propio contra 2-3 URLs reales del diagnóstico del 12-06 antes de
  codificar el parseo definitivo (mismo método que 17.3/19.1).

Dependencias: R23 requiere R20 (result_type) implementado. No bloquea las tareas 1-15.

---

### R24 — Vocabulario ODS en queries del investigador

El investigador ampliará su vocabulario de búsqueda con términos alineados con
los Objetivos de Desarrollo Sostenible (ODS) y la Agenda 2030, para captar
convocatorias que se anuncien con lenguaje de cooperación internacional.

**R24.1** El vocabulario ODS se carga desde un archivo YAML ubicado en
`src/agente_ong/research/` (nombre exacto definido en `tasks.md`).

**R24.2** Los términos ODS se combinan con el vocabulario base de convocatoria
de R16. No se lanzan como queries independientes sin contexto de convocatoria.

**R24.3** El archivo YAML se estructura en tres categorías para facilitar
mantenimiento: `ods_generales`, `cooperacion_espanola`, `enfoques_transversales`.

**R24.4** Si el archivo YAML falta o está mal formado, el investigador registra
el fallo en el log y continúa con un vocabulario de reserva embebido en código
(los 5 términos ODS más generales). El sistema no debe detenerse por un error de
configuración de vocabulario.

**Tope operativo:** máximo 5 queries ODS adicionales por ciclo del investigador.
Cada una combina un término ODS con vocabulario base de convocatoria.

**Fallback en código (activado solo si el YAML falla):**
1. "Agenda 2030"
2. "ODS"
3. "Objetivos de Desarrollo Sostenible"
4. "Plan Director cooperación española"
5. "subvenciones 0,7%"

---

### R25 — Selección de ODS por el usuario en la generación de queries

El investigador sustituye el vocabulario ODS fijo de R24 por una selección
explícita del usuario, para que las queries ODS reflejen la intención real de
cada búsqueda.

**R25.1** El usuario selecciona los ODS relevantes para su búsqueda desde la
UI, mediante un componente de multiselección obligatoria (mínimo 1 ODS
elegido), a partir de los 17 ODS oficiales de la ONU con su nombre completo
(ej. "ODS 1 - Fin de la pobreza").

**R25.2** Las queries ODS se generan solo a partir de los ODS elegidos por el
usuario: N ODS elegidos producen N queries ODS. Esta selección reemplaza al
vocabulario fijo del YAML de R24 como fuente de términos ODS.

**R25.3** El archivo `ods_vocabulary.yaml` (R24) se mantiene como fallback
defensivo: si la UI enviara una lista de ODS vacía por un bug, el investigador
recurre al vocabulario fijo de R24 en vez de omitir las queries ODS.

**Motivo de la reapertura:** hallazgo abierto de la prueba humana del
05-07-2026 (desaparición de resultados Tavily por saturación del pool de hits
con las 5 queries ODS genéricas fijas de R24 — ver decisión pendiente #13 en
`Contexto_para_mi/decisiones_pendientes.md`) y problema de fondo: las queries
ODS fijas no reflejan la intención real del usuario en cada búsqueda.

---

## Decisiones tomadas (12-06-2026, Kike)

- **P1 — opción (b):** Tavily fuente secundaria para subvenciones (ver 16.5). Se conserva
  activable por su valor como material RAG futuro (proyectos redactados).
- **P2 — dos informes:** resumido para el usuario + detallado para análisis (R22).
- **P3 — confirmada** la promoción del detalle BDNS (R19) desde v1.1 a esta spec.

---

## Fuera de alcance de la reapertura 05-07-2026

Omisiones conscientes, no olvidos. Registradas para futuras lecturas del código.

### R24.5 — Edición del vocabulario ODS por el usuario final

Ofrecer a la ONG usuaria una interfaz en Streamlit para editar el archivo YAML
desde la aplicación, sin tocar código ni repositorio.

**Estado:** aplazado a spec futura (candidato SPEC 5 o SPEC 6).

**Motivo del aplazamiento:**
1. Requiere trabajo de UI (edición, guardado, feedback).
2. Requiere validación del contenido editado (YAML mal formado, vocabulario vacío).
3. Requiere persistencia real: en Streamlit Cloud el sistema de archivos es
   efímero; habría que usar SQLite u otro almacenamiento persistente.
4. Requiere decisiones de multi-usuario (¿comparten vocabulario o cada ONG el
   suyo?).
5. La ONG usuaria no puede editar bien lo que aún no funciona. Primero verificar
   que el vocabulario ODS fijo trae resultados de calidad; sin esa base no se
   sabe qué necesita editar el usuario.

**Consecuencia:** en esta reapertura el YAML es editable solo por el
desarrollador, con cambios versionados en Git.

### R25.4 — Persistencia de ODS en el modelo Opportunity

Guardar los ODS elegidos por el usuario (o detectados) como campos del
modelo `Opportunity` (p.ej. `ods_principal`, `ods_secundarios`).

**Estado:** aplazado a spec futura. Ver decisión pendiente #16 en
`Contexto_para_mi/decisiones_pendientes.md`.

**Motivo del aplazamiento:** requiere una decisión de diseño previa (¿un ODS
principal + lista de secundarios, o lista plana?) que puede depender de las
necesidades de SPEC 4 (redactor con Marco Lógico).

### Fuentes nuevas de convocatorias

`pendientes_ods_investigador.md` sección 3 lista candidatas (Ministerio Derechos
Sociales, ACNUDH, ONU Mujeres). Quedan fuera: añadir fuentes es cambio
estructural, no retoque de vocabulario.

### Campos ODS en el modelo `Opportunity`

`pendientes_ods_investigador.md` sección 2 propone `ods_principal`,
`ods_secundarios`, `prioridad_geografica`, `enfoques_transversales`,
`plan_director_alineacion`. Quedan fuera: requieren decisión de diseño previa
(extracción automática con LLM vs. metadata manual) que no procede resolver en
esta reapertura.
