# Design Document — investigador-v2

## Overview

Corrige los defectos diagnosticados en la primera prueba de producción (12-06-2026: 212
resultados, 0 convocatorias útiles) tocando principalmente `src/agente_ong/research/`.
Cuatro frentes: (1) la verificación cruzada deja de contar duplicados (R14); (2) el mix de
fuentes se ajusta al modo subvenciones — TED fuera, Tavily secundaria y con vocabulario de
convocatoria y filtro temporal (R15/R16/R17); (3) el contenido se limpia y se acota, y BDNS
aporta importe y plazo desde su endpoint de detalle (R18/R19); (4) los resultados se
pre-clasifican (`result_type`, R20) y el informe gana una vista resumida (R22). R21 cierra
con una re-validación manual contra los casos reales.

Nota de alcance: el grueso vive en `research/`; los requisitos 15.3, 20.2 y R22 citan
explícitamente cambios MÍNIMOS en la capa UI (`app.py`, `report_serde.py`,
`report_view.py`), que esta spec asume como parte de su alcance (la frase "solo research/"
de la introducción se interpreta como "sin rediseños de UI": los retoques de UI son los
enumerados por los propios requisitos y nada más).

## Steering Document Alignment

Sin cambios de stack (tech.md): mismas fuentes, SQLite, Streamlit. La abstracción
`SearchSource` se conserva; los ajustes son atributos opcionales con defaults
retrocompatibles. structure.md intacto: módulos nuevos (`textclean.py`, `triage.py`) bajo
`src/agente_ong/research/`, tests espejo en `tests/research/`.

## Decisiones de diseño por requisito

### R14 — Deduplicación de fuentes en la verificación

**Dónde:** `verification.py` (conteo) + `graph.py::_classified` (lista visible del informe).

1. Helper nuevo `dedupe_refs(refs: Sequence[SourceRef]) -> list[SourceRef]` en
   `verification.py`: colapsa por `normalize_url(ref.url)` (reutiliza `urlnorm`, la misma
   normalización del ledger). Orden estable; ante duplicado se conserva la referencia
   OFICIAL si la hay (la oficialidad no debe perderse al colapsar), si no la primera.
2. `VerificationPolicy.classify` deduplica `supporting` ANTES de contar (defensa en
   profundidad: cualquier llamador queda protegido). VERIFIED ⇔ 2+ URLs normalizadas
   DISTINTAS (14.2); el resto de reglas (oficialidad, conflicting, not_found) no cambian.
3. `graph._classified` asigna `claim.sources = dedupe_refs(refs)` — el informe nunca
   muestra URLs repetidas (14.3).

**Consecuencia asumida (a confirmar por Kike):** las convocatorias se agrupan POR URL en
`_build_opportunities`, así que tras R14 todas las refs de un grupo colapsan a una → los
resultados de búsqueda serán como máximo `OFFICIAL_UNCROSSED` (BDNS) o
`UNCROSSED_UNVERIFIED` (Tavily). `VERIFIED` queda reservado a corroboración real entre
URLs DISTINTAS, que hoy no se produce en la fase de búsqueda — es lo correcto: el
"Verificado" actual era falso. La corroboración multi-URL genuina llegará con la
agrupación semántica de convocatorias (SPEC 2+). El test existente
`test_cross_verification_statuses` se actualiza documentando este cambio de regla.

### R15 — TED excluido del modo subvenciones

**Dónde:** `sources/base.py`, `sources/ted.py`, `graph.py::_active_sources`, `ui/app.py`.

- `SearchSource` gana el atributo de clase `excluded_modes: frozenset[ResearchMode] =
  frozenset()` (default vacío = comportamiento actual, retrocompatible).
- `TedSource.excluded_modes = frozenset({"calls"})` — el código y sus tests se conservan
  íntegros para el futuro modo "licitaciones" (15.2).
- `graph._active_sources` añade el filtro `request.mode not in source.excluded_modes`
  (15.1). `_default_sources` SIGUE construyendo TedSource: el filtro es por modo, no por
  existencia.
- UI (15.3): se elimina la entrada `"ted"` de `_SOURCE_LABELS` en `app.py` (la UI solo
  lanza `mode="calls"` hoy). Cambio de una línea + ajuste del test del multiselect.

**Evidencia (15.4):** en los informes del 12-06-2026, el 100% de los resultados TED fueron
licitaciones (compra de vehículos, mantenimiento de edificios, software); TED publica
contratación pública por encima de umbral, no subvenciones, y su full-text matchea incluso
contra el nombre del organismo ("Consejería de... Soberanía Alimentaria"). Ya estaba
documentado en `ted.py` que TED "no es la fuente principal para ONGs"; la v2 lo hace
efectivo en el modo subvenciones.

### R16 — Vocabulario de convocatoria en Tavily

**Dónde:** `config.py`, `sources/tavily.py`.

- Lista exacta (DEFAULT, configurable): `("convocatoria", "subvención", "ayudas",
  "bases reguladoras", "plazo de presentación")`. Vive como
  `DEFAULT_CALL_VOCABULARY` en `config.py`; campo `call_vocabulary: tuple[str, ...]` en
  `ResearchConfig` (default la constante) + env `RESEARCH_CALL_VOCABULARY` (lista separada
  por comas) en `from_env()`.
- Composición de la query en `TavilySource.search` (16.1/16.3):
  `"{search_context} {términos} {vocabulario}"` donde `{vocabulario}` es la lista unida por
  espacios — Tavily es búsqueda en lenguaje natural, los términos extra orientan el
  ranking hacia la OFERTA de financiación sin operadores frágiles. El `search_context`
  del proyecto se mantiene delante (se complementa, no se sustituye).
- BDNS no se toca (16.2): su corpus ya es exclusivamente subvenciones.
- Test (16.4): con cliente fake, capturar el texto enviado y asertar que contiene al menos
  un término del vocabulario y que el `search_context` sigue presente.

**Tavily como fuente secundaria (16.5, decisión P1-b):** se materializa en la heurística de
R20 — los hits de Tavily se clasifican como máximo `documento_informativo` salvo señal
fuerte de convocatoria (ver R20). Razón documentada: la prueba de producción mostró que
Tavily devuelve mayoritariamente la EJECUCIÓN de fondos (proyectos ya financiados,
estudios, noticias), no la oferta; pero ese material es valioso como contexto y como
ejemplos de proyectos redactados para el RAG/redactor (SPEC 3/4), así que sigue activable
y sus resultados se conservan, señalizados.

### R17 — Filtro temporal en Tavily

**Dónde:** `sources/tavily.py`, `models.py` (SearchHit), `investigador.py` (wiring).

- `SearchHit` gana dos campos retrocompatibles: `published_year: int | None = None`
  (año identificado del resultado) — los consumidores actuales no cambian.
- `TavilySource(min_year: int | None = None)`, cableado en `_default_sources` con
  `config.min_year` (igual que BDNS).
- Fecha identificable (17.1, conservador para no inventar antigüedad):
  1. el campo `published_date` del resultado de Tavily, si viene;
  2. si no, un año `(19|20)\d{2}` en el TÍTULO (el caso real: "… Noviembre 2009").
     El cuerpo/snippet NO se usa (citar un año no fecha el documento).
- Con año identificado < `min_year` → descartado; sin año identificable → se conserva con
  `published_year=None`, que el informe refleja como fecha desconocida (17.2). La marca
  `date_unknown` del requisito se materializa como `published_year is None` (sin campo
  booleano redundante).
- 17.3: en el momento de implementar se verifica EN VIVO (una llamada, mismo método que
  BDNS/TED) si la versión instalada de tavily-python soporta `time_range`/`days`; si sí,
  se pasa el equivalente más conservador además del filtro en cliente (el filtro en
  cliente es la garantía; el parámetro de API, una optimización).

### R18 — Limpieza del contenido extraído

**Dónde:** módulo nuevo `research/textclean.py` + aplicación en `graph.py`; límites en
`config.py`.

- `textclean.clean_text(text) -> str`: filtro por líneas con lista de patrones de
  plantilla web (case-insensitive): cookies ("cookie", "política de privacidad",
  "aviso legal"), navegación ("skip to content", "menú", "inicio |", breadcrumbs),
  selectores de idioma (líneas cortas tipo "ES / CAT / EN"), suscripción ("newsletter",
  "suscríbete", "boletín"), redes sociales, y descarte de líneas de solo enlaces/muy
  cortas repetidas. Además: colapso de espacios y de líneas duplicadas consecutivas.
  Heurístico y mejorable; el objetivo es la "mejora drástica", no la perfección (18.1).
- Límites configurables en `ResearchConfig` (+ env): `snippet_max_chars: int = 300`
  (RESEARCH_SNIPPET_MAX_CHARS) para los snippets por campo (18.2) y
  `organism_max_chars: int = 200` (RESEARCH_ORGANISM_MAX_CHARS) para el campo Organismo
  (18.3). `textclean.snippet(text, max_chars)` trunca en límite de palabra con elipsis.
- Aplicación en `graph.py`: `_build_opportunities` pasa el snippet del organismo por
  `clean_text` + `snippet(…, organism_max_chars)`; `_summarize` (ledger) usa `clean_text`
  antes de truncar. El detalle completo del documento NO se pierde: la vista detallada
  (R22) muestra el contenido limpio pero no truncado a nivel de campo.

### R19 — BDNS: llamada al detalle (importe y plazo)

**Dónde:** `sources/bdns.py`, `models.py` (SearchHit), `config.py`, `graph.py`.

- **Verificación previa en vivo** (mismo método que en la integración original): UNA
  llamada a `/convocatorias?numConv=...&vpd=GE` para confirmar los nombres reales de los
  campos de importe (`presupuestoTotal`, ya investigado) y de plazo
  (`fechaInicioSolicitud`/`fechaFinSolicitud` o equivalentes) antes de codificar el parseo.
- `SearchHit` gana campos retrocompatibles `amount: str | None = None` y
  `deadline: str | None = None` (solo BDNS los rellena por ahora).
- En `BdnsSource`: tras `_to_hits` (que YA aplica `min_year` — 19.2 se cumple por orden de
  operaciones), se enriquecen los primeros N hits supervivientes con el detalle;
  `N = config.bdns_max_detail_calls` (nuevo campo, default 20, env
  RESEARCH_BDNS_MAX_DETAIL_CALLS — 19.3). Cada detalle usa `with_retry` como el resto de
  llamadas; un fallo de detalle no descarta el hit (se queda sin importe/plazo, 19.4) ni
  aborta los demás.
- `graph._build_opportunities` usa los campos nuevos: `amount_val = next((h.amount for h
  in group if h.amount), None)` (ídem deadline), con las refs de los hits que aportaron el
  dato. Importe/plazo de BDNS pasan así de `NOT_FOUND` a `OFFICIAL_UNCROSSED` con su
  trazabilidad (la URL pública de la convocatoria como SourceRef). Sin dato → `None` →
  `NOT_FOUND`, como hoy (19.4, nunca inventar).

### R20 — `result_type` (preparación del filtrado semántico)

**Dónde:** módulo nuevo `research/triage.py`, `models.py`, `graph.py`; serde/vista en UI.

- Alias `ResultType = Literal["convocatoria_probable", "documento_informativo",
  "desconocido"]` en `models.py`. Campos retrocompatibles: `SearchHit.result_type:
  ResultType = "desconocido"` y `GrantOpportunity.result_type: ResultType =
  "desconocido"` (20.3).
- `triage.classify_hit(hit) -> ResultType` — heurística provisional (20.1):
  - hit de BDNS → `convocatoria_probable` (su corpus es solo convocatorias);
  - señales fuertes en título/snippet (≥2 de: "convocatoria", "bases reguladoras",
    "plazo de presentación"/plazo con fecha, importe con €/cifra) o dominio oficial
    (`.gob.es`, `europa.eu`, sede electrónica) → `convocatoria_probable`;
  - hit de Tavily sin señal fuerte → `documento_informativo` (tope de 16.5);
  - resto → `desconocido`.
- `graph._build_opportunities` asigna a cada opportunity el mejor tipo de su grupo
  (orden: `convocatoria_probable` > `desconocido` > `documento_informativo`).
- UI mínima (20.2): `report_serde` serializa el campo con default retrocompatible
  (`data.get("result_type", "desconocido")` — los informes ya persistidos cargan sin
  error); `report_view` agrupa los `documento_informativo` en una sección aparte
  ("Material informativo, no convocatorias") tanto en el render como en el Markdown.

### R22 — Dos vistas del informe (decisión P2)

**Dónde:** `ui/report_serde.py`, `ui/report_view.py` (y descargas en el render).

- Funciones desde el MISMO dict persistido (22.4 — sin segunda investigación):
  - `report_to_markdown_summary(report)`: por convocatoria, una ficha de pocas líneas —
    título, organismo, importe, plazo, URL y estado de verificación (22.1); secciones
    breves de no-resuelto/fuentes caídas; los `documento_informativo` listados aparte
    solo con título + URL.
  - `report_to_markdown(report)` se mantiene como vista DETALLADA (22.2), beneficiada de
    la limpieza R18 (los valores ya llegan limpios/acotados).
- `render_report`: muestra la vista resumida por defecto; un expander/toggle "Ver informe
  detallado" da acceso al completo; DOS botones de descarga (resumido / detallado)
  (22.3). El smoke E2E se ajusta a la nueva estructura.

### R23 — Lectura profunda sin dependencia de créditos

**Dónde:** módulo nuevo `sources/reader.py`, `config.py`, `graph.py::read_deep`,
`investigador.py` (wiring), `ui/app.py` (etiqueta), `requirements.txt` (trafilatura).

**Dónde encaja el adapter (verificado en código):** no existe un "puerto de lectura"
separado — la capacidad `fetch` de `SearchSource` ES el puerto de lectura
(`FirecrawlSource` es un `SearchSource` con `capabilities={"fetch"}` y `read_deep` usa los
fetchers activos). `HttpReaderSource` implementa por tanto `SearchSource` con
`capabilities={"fetch"}`, `name="reader"`, `is_official=False` — mismo puerto, cero
cambios de interfaz (23.1).

- **HttpReaderSource (23.1):** `httpx.Client` (timeout, User-Agent de navegador) +
  `trafilatura.extract()` para el texto principal (descarta plantilla web en origen;
  `textclean` de R18 sigue aplicándose después — complementa, no sustituye). Enlaces
  salientes: `trafilatura` no los devuelve → se extraen los `href` absolutos http(s) del
  HTML (regex/lxml), deduplicados y acotados (~50) para alimentar la profundización como
  hacía Firecrawl. Reintentos con `with_retry` (a diferencia de firecrawl-py, httpx no
  reintenta solo). Extracción vacía ⇒ se trata como fallo de lectura (dispara fallback).
  Dependencia nueva sin coste: `trafilatura` en requirements.txt.
- **Orquestación primario/fallback (23.2):** vive en `graph.read_deep`. Los fetchers
  activos se ordenan: el PRIMERO es el primario (reader; `_default_sources` lo construye
  siempre — no necesita clave) y el resto son fallback (Firecrawl, construido solo si hay
  api_key). Por cada URL: primario → si falla (excepción tras reintentos o documento
  vacío) y quedan llamadas de fallback (`firecrawl_max_calls`, contador POR investigación)
  → fallback. Con `firecrawl_max_calls=0` (default) el fallback nunca se invoca: coste
  cero garantizado (23.4).
- **Gating por result_type (23.3), solo en modo "calls":** en modo "calls" la frontera de
  `read_deep` solo se siembra con hits `result_type == "convocatoria_probable"`. Las
  `direct_urls` del usuario SIEMPRE se leen (petición explícita, R9). Los enlaces salientes
  de páginas ya leídas heredan la elegibilidad de su página origen (vienen de una
  convocatoria probable). En modo "training" el gating se desactiva a propósito: todos los
  hits siembran la frontera (el material informativo/desconocido es el objetivo de ese
  modo). Cubierto por test_read_deep_in_training_mode_fetches_all_hits.
- **Límites (23.4):** `reader_max_pages: int = 15` (propuesta; máximo de páginas leídas
  en profundidad por búsqueda, env RESEARCH_READER_MAX_PAGES — coexiste con `max_pages`:
  gana el menor) y `firecrawl_max_calls: int = 0` (env RESEARCH_FIRECRAWL_MAX_CALLS).
- **Fallo sin descarte (23.5):** como hoy — el hit conserva sus datos de búsqueda; el
  fallo se anota en `failed_sources` y el ledger registra `outcome="error"`; el informe
  refleja que esa URL no se pudo leer en profundidad.
- **UI (consecuencia mínima, análoga a 15.3):** la entrada `"firecrawl"` de
  `_SOURCE_LABELS` pasa a `"reader"` con etiqueta "Lectura de páginas y URLs directas"
  (el lector propio es el que la UI activa/desactiva; Firecrawl ya no es una fuente que
  el usuario elija — es un fallback de configuración).
- **Verificación en vivo (23.6):** antes de fijar el parseo, UNA pasada del lector propio
  contra 2-3 URLs reales del diagnóstico del 12-06 (las que Firecrawl falló o llenó de
  plantilla); los tests de la suite usan fakes HTTP (patrón `_FakeHttp`).

### R21 — Re-validación con casos reales (manual)

Tarea conjunta con Kike, NO autónoma: re-ejecutar las dos búsquedas del 12-06-2026
(mismos términos y contexto) y comparar las métricas de 21.1. El antes/después se
documenta en `Contexto_para_mi/revalidacion_investigador_v2.md` (material de
portafolio, 21.2). La validación de criterio fino queda para testers expertos (21.3).

## Orden de implementación y dependencias

R14 (independiente) → R15 (independiente) → R16/R17 (tocan TavilySource; R17 añade campos
a SearchHit) → R18 (textclean, independiente) → R20 (necesita los campos de SearchHit y
conviene antes que R19 para clasificar también los hits enriquecidos) → R19 (usa
SearchHit.amount/deadline) → R22 (necesita R18 y R20 para que la vista detallada y la
agrupación tengan sentido) → R23 (requiere R20: el gating de lectura usa result_type; no
bloquea nada anterior) → R21 (manual, al final, con todo integrado).

## Error Handling

- Detalle BDNS caído o sin campos esperados: el hit conserva sus datos de búsqueda, sin
  importe/plazo (NOT_FOUND); el error de red se reintenta con `with_retry` y, agotado, no
  aborta el resto (coherente con Reliability v1).
- `published_date` de Tavily con formato inesperado: se ignora (equivale a "sin fecha
  identificable", 17.2).
- Informes persistidos ANTES de v2: `report_from_dict` aplica defaults (`result_type` →
  "desconocido"); las dos vistas funcionan sobre informes antiguos.

## Testing Strategy

- **R14:** unit en `test_verification.py` (misma URL 3x → 1 fuente; oficial sobrevive al
  colapso) + regresión de integración en `test_graph_flow.py` (caso real del diagnóstico);
  actualización documentada del test de verificación cruzada v1.
- **R15:** `_active_sources` con mode="calls" excluye TED; TedSource intacto (sus tests
  v1 no se tocan); UI sin TED en el multiselect.
- **R16:** query capturada con cliente fake contiene vocabulario + contexto; BDNS recibe
  el término sin alterar.
- **R17:** descarte por `published_date` antigua; descarte por año antiguo en el título;
  sin fecha → se conserva con `published_year=None`; `min_year=None` no filtra.
- **R18:** unit de `textclean` (cookies/nav/idiomas fuera; texto útil intacto; límites);
  integración: organismo acotado en el informe.
- **R19:** con `_FakeHttp`: detalle rellena amount/deadline; límite de llamadas
  respetado; min_year antes del detalle (no se llama al detalle de descartados); fallo de
  detalle no rompe; informe con importe/plazo OFFICIAL_UNCROSSED.
- **R20:** heurística por casos (BDNS, Tavily con/sin señales, dominio oficial); serde
  retrocompatible (dict viejo sin el campo); agrupación en la vista.
- **R22:** resumen con los 6 campos y pocas líneas; ambas vistas desde el mismo dict;
  smoke E2E ajustado.
- **R23:** unit de `HttpReaderSource` con fakes HTTP (`_FakeHttp`): documento con texto y
  enlaces salientes; HTML solo-plantilla → extracción vacía tratada como fallo; sin red →
  fallo controlado. Integración en `read_deep`: solo los hits `convocatoria_probable`
  disparan lectura (los `documento_informativo`/`desconocido` no); `direct_urls` siempre se
  leen; fallo del primario con `firecrawl_max_calls=0` → sin fallback, hit conservado y
  fallo reflejado; con `firecrawl_max_calls=N` → fallback invocado como máximo N veces;
  `reader_max_pages` respetado. Más UNA verificación en vivo del lector contra 2-3 URLs
  reales del diagnóstico del 12-06 antes de fijar el parseo (23.6). `reader_max_pages`
  por defecto = 15.
