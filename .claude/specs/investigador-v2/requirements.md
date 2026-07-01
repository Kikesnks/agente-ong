# Spec investigador-v2 — requirements.md (APROBADO por Kike el 12-06-2026)

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

## Decisiones tomadas (12-06-2026, Kike)

- **P1 — opción (b):** Tavily fuente secundaria para subvenciones (ver 16.5). Se conserva
  activable por su valor como material RAG futuro (proyectos redactados).
- **P2 — dos informes:** resumido para el usuario + detallado para análisis (R22).
- **P3 — confirmada** la promoción del detalle BDNS (R19) desde v1.1 a esta spec.
