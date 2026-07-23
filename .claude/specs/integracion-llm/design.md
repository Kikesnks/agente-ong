# Design Document — integracion-llm (SPEC 2)

## Overview

Dos piezas: (1) una abstracción multi-proveedor de LLM (`R1`-`R5`) con el mismo patrón
Ports & Adapters que ya usa el investigador (`SearchSource`, `ResearchStore`); (2) su
primer consumidor real, un filtro semántico mínimo (`R6`) que clasifica cada resultado de
una investigación como convocatoria abierta o no. El filtro es una capa **nueva y aditiva**
por encima de `research/`: no toca `graph.py`, `triage.py` ni ningún código ya testeado del
investigador, y en particular no altera `R20` de `investigador-v2` (`result_type`).

## Steering Document Alignment

- `tech.md`: "Multi-proveedor... abstrae el proveedor... Claude, OpenAI y otros"; "LangChain
  para... integraciones de modelos"; "configurar el proveedor/modelo mediante variables de
  entorno; nunca hardcodear claves". Esta spec materializa exactamente esa decisión.
- `structure.md`: el módulo vive en `src/agente_ong/llm/` ("abstracción multi-proveedor de
  LLM"), ya reservado en la estructura de carpetas propuesta. Convención de nombres
  (`snake_case` módulos, `PascalCase` clases) y tests espejo en `tests/llm/`.
- Patrón ya validado en el repo: `research/sources/base.py` (`SearchSource` ABC +
  `with_retry`) y `research/store/base.py` (`ResearchStore` ABC + `InMemoryStore` fake para
  tests). El puerto `LLMProvider` y su mock siguen el mismo molde.

## Decisiones de diseño por requisito

### R1 — Puerto `LLMProvider`

**Dónde:** módulo nuevo `src/agente_ong/llm/provider.py`.

- **Firma B (decisión):** `complete(system: str, user: str) -> LLMResponse`, con `system` y
  `user` **separados** en vez de un prompt único concatenado por el llamador. Razones:
  1. Separa instrucciones (system) de datos (user) — más robusto frente a inyección de
     contenido de terceros en el user prompt (el snippet de un resultado de búsqueda, en
     R6, es contenido no confiable).
  2. Alinea con SPEC 3 (chat de proyecto), que necesitará roles (system/user/assistant) de
     todas formas; adoptar la separación ahora evita un cambio de firma más adelante.
- `LLMProvider(ABC)` con un único método abstracto `complete`. Mismo molde que
  `SearchSource`/`ResearchStore`: ABC + implementaciones intercambiables.
- `LLMResponse` (`dataclass`, en el mismo módulo): `text: str`, `input_tokens: int`,
  `output_tokens: int`. Sin campos de streaming ni de coste (R5.2, fuera de alcance).
- Consecuencia de R1.2 (nada fuera de los adaptadores importa LangChain): `provider.py` no
  importa `langchain` ni ningún SDK de proveedor — solo define el contrato con tipos de la
  stdlib.

### R2 — Adaptadores Claude, OpenAI y Ollama

**Dónde:** `src/agente_ong/llm/adapters/claude.py`, `openai.py`, `ollama.py` (paquete
`adapters/` bajo `llm/`, cada adaptador en su propio módulo — mismo patrón que
`research/sources/*.py`, uno por fuente).

- Cada adaptador implementa `LLMProvider` usando el `ChatModel` de LangChain
  correspondiente (`langchain-anthropic`, `langchain-openai`, `langchain-ollama`); los
  nombres exactos de las clases LangChain y su mapeo a `LLMResponse` (incluida la
  extracción de `usage_metadata`/tokens de cada integración, que difiere por proveedor) se
  fijan al implementar (T3/T4), verificando en vivo el formato de respuesta de cada
  librería antes de codificar el parseo — mismo método de verificación que R17.3/R19.1 de
  `investigador-v2`.
  Nota de dependencias: `langchain>=0.3` ya está en `requirements.txt`; T3/T4 añaden
  `langchain-anthropic`, `langchain-openai` y `langchain-ollama`.
- Ollama no exige clave (R2.3): su adaptador se construye solo con `base_url`/`model`.
- El adaptador genérico OpenAI-compatible (R2.4) no se implementa aquí; queda anotado en el
  roadmap como candidato de backlog (mismo patrón que usaría `langchain-openai` apuntando a
  un `base_url` distinto, pero sin las particularidades de Claude/OpenAI/Ollama que sí se
  cubren).

### R3 — Configuración

**Dónde:** módulo nuevo `src/agente_ong/llm/config.py`, mismo patrón que
`research/config.py` (`dataclass` + `from_env()`). Alcance ampliado 23-07-2026 (ver
`requirements.md` R3, commit `58ccd1f`): T5 se desbloquea con selección multi-proveedor
por entorno, sin esperar a Claude (T4b sigue aplazada).

- `LLMConfig` (`dataclass`): `provider: Literal["ollama", "deepseek", "openai",
  "disabled"]`, `provider_explicit: bool` (`True` si `LLM_PROVIDER` estaba definida en
  el entorno; `False` si no estaba y se usó el default — ver más abajo), `temperature:
  float = 0.0` (determinismo por defecto, apropiado para el filtro SI/NO de R6),
  `deepseek_api_key: str | None = None`, `openai_api_key: str | None = None` (Ollama no
  lleva campo de clave: no la requiere, R3.3). Sin campo `model`: el modelo y el
  `base_url` de cada proveedor de pago son presets internos del código (ver bullet de
  presets, más abajo), no parte de `LLMConfig`.
- `LLMConfig.from_env()` lee `LLM_PROVIDER`, `LLM_TEMPERATURE`, `DEEPSEEK_API_KEY`,
  `OPENAI_API_KEY` (mismo patrón que `ResearchConfig.from_env()`:
  `load_dotenv(env_path, override=False)` antes de leer, R3.6). Lee TODAS las claves
  presentes en el entorno (R3.3) sin validar que la del proveedor seleccionado exista —
  esa comprobación vive en `build_provider`, no en la construcción de `LLMConfig`
  (mismo principio que `ResearchConfig`: una clave ausente no rompe la construcción,
  solo el uso). Si `LLM_PROVIDER` no está definida: `provider = "ollama"`,
  `provider_explicit = False` — preserva el comportamiento actual (`jobs.py:182` intenta
  Ollama incondicionalmente hoy, sin ninguna variable de por medio). Si está definida
  (a cualquier valor, válido o no): `provider_explicit = True`. **Confirmado con Kike
  (23-07-2026).**
- **Presets internos por proveedor de pago:** un diccionario privado en `config.py`
  (p. ej. `_PAID_PROVIDER_PRESETS: dict[str, tuple[str, str]]`, clave = nombre de
  proveedor, valor = `(base_url, model)`) para `deepseek` y `openai`. Sin variable de
  entorno equivalente a `LLM_BASE_URL`/`LLM_MODEL` (fuera de alcance). Los valores
  concretos se fijan en `tasks.md` al implementar; la verificación en vivo contra
  DeepSeek queda como paso manual posterior, fuera de esta ronda (mismo principio de
  verificación que T3/T4a).
- `build_provider(config: LLMConfig) -> LLMProvider | None` — **cambio de firma
  respecto al diseño original:** ya no devuelve siempre un `LLMProvider`, puede devolver
  `None`. Fábrica única, sin excepciones, que resuelve el fallback silencioso completo
  (R7.3):
  - `config.provider == "disabled"` → `None`.
  - `config.provider == "ollama"` → `None` si `is_ollama_available()` es `False`; si no,
    `OllamaProvider(model=...)` (mismo preset ya usado hoy en `jobs.py::_OLLAMA_MODEL`).
  - `config.provider in ("deepseek", "openai")` → `None` si falta la clave
    correspondiente; si no, `OpenAICompatibleProvider` con el preset de
    `base_url`/`model` de ese proveedor y la clave leída.
  - Cualquier valor de `provider` no reconocido → `None` (nunca excepción — mismo
    principio de "nunca lanza" que `is_ollama_available`).
  Es el único punto del código, fuera de los propios adaptadores, que conoce los cuatro
  nombres de proveedor; sustituye directamente el hardcodeo de `OllamaProvider(model=
  _OLLAMA_MODEL) if is_ollama_available() else None` en `ui/jobs.py:182`.
- **Healthcheck del sidebar (R7.7):** `build_provider` por sí solo no basta para el
  aviso — el sidebar necesita saber el MOTIVO cuando el resultado es `None` (`disabled`
  vs. sin clave vs. no disponible), y también cuándo `LLM_PROVIDER` ni siquiera estaba
  definida, aunque el proveedor por defecto SÍ esté disponible. Nueva función
  `describe_llm_status(config: LLMConfig) -> tuple[LLMProvider | None, str | None]` en
  `config.py` (envuelve la misma resolución de `build_provider` y añade el mensaje
  legible; decisión de implementación exacta — un solo cálculo o dos — para
  `tasks.md`). El mensaje distingue cinco combinaciones:
  - `disabled` → "filtro desactivado por configuración".
  - proveedor de pago sin clave → "`deepseek` configurado pero falta
    `DEEPSEEK_API_KEY`".
  - proveedor inalcanzable → "`ollama` configurado pero no responde".
  - proveedor disponible, con `LLM_PROVIDER` definida explícitamente
    (`provider_explicit = True`) → mensaje `None`, sin aviso.
  - `provider_explicit = False` (variable ausente, se usó el default) → mensaje
    informativo SIEMPRE presente, tanto si `ollama` responde como si no:
    "`LLM_PROVIDER` no definida, usando `ollama` por defecto" (combinado con el motivo
    de indisponibilidad si además `ollama` no responde). Es la única combinación en la
    que el sidebar muestra un mensaje aunque el proveedor SÍ esté disponible —
    informativo, no de alarma (estilo visual distinto al warning de "no disponible";
    decisión de UI para `tasks.md`).

### R4 — Errores y reintentos

**Dónde:** módulo nuevo `src/agente_ong/llm/errors.py` + aplicación en cada adaptador.

- Jerarquía propia: `LLMError` (base), `LLMConnectionError` (red caída),
  `LLMAuthError` (clave inválida/ausente), `LLMNoResponseError` (proveedor sin respuesta
  útil, p.ej. timeout tras reintentos). Cada adaptador captura las excepciones específicas
  de su SDK LangChain y las traduce a una de estas (R4.1) — nunca deja escapar la excepción
  cruda.
- Reintentos: se reutiliza el patrón `with_retry` de `research/sources/base.py` (backoff
  exponencial) para `LLMConnectionError`/timeouts (R4.2); `LLMAuthError` **no** se
  reintenta (R4.3, no es transitorio). Decisión de implementación: extraer `with_retry` a
  un módulo compartido o importarlo desde `research/sources/base.py` se decide en T2, sin
  duplicar la lógica de backoff.

### R5 — Contador de tokens

**Dónde:** `LLMResponse` (R1) + relleno en cada adaptador (R2).

- No hay módulo propio: el contrato ya vive en `LLMResponse.input_tokens`/`output_tokens`
  (R1.1); cada adaptador (T3/T4) rellena esos campos a partir del `usage_metadata` que
  expone su integración LangChain concreta. Sin lógica de presupuesto ni límites (R5.2).

### R6 — Filtro semántico (Opción 1)

**Dónde:** módulo nuevo `src/agente_ong/llm/semantic_filter.py` +
`src/agente_ong/llm/prompts/semantic_filter.md`.

- **Contrato de respuesta única para los tres proveedores:** el prompt fuerza al modelo a
  responder **únicamente** "SI" o "NO", sin JSON ni function calling. Justificación: Ollama
  soporta peor la salida estructurada específica de proveedor (JSON mode/function calling),
  y usarla rompería el contrato único del puerto `LLMProvider` (R1.3) al obligar a ramas
  por proveedor en el consumidor. El "no clasificado" **no** se le pide al modelo — lo
  asigna el código cuando la respuesta no es interpretable como SI/NO (R6.4), p.ej. usando
  una normalización estricta (`strip().upper()` y comparación exacta) antes de aceptar
  SI/NO.
- **Prompt en archivo `.md` aparte** (`llm/prompts/semantic_filter.md`), cargado por código
  — mismo patrón "skill" que usará el agente redactor de SPEC 4. Refinar el prompt (ajustar
  ejemplos de falsos positivos, redacción) no debe tocar código Python. T6 implementa el
  cargador (`load_prompt(name: str) -> str`, lectura simple del archivo).
- **Estructura del prompt** (6 piezas, todas en el archivo salvo la 6ª):
  1. Rol: clasificador experto en convocatorias de subvención de cooperación internacional
     para ONGs.
  2. Pregunta exacta: "¿es esto una convocatoria de subvención ABIERTA a la que una ONG
     puede presentarse?".
  3. Qué cuenta como SÍ: una convocatoria vigente (plazo abierto o no vencido) que ofrece
     financiación a la que una organización puede presentar una solicitud.
  4. Qué cuenta como NO, con los falsos positivos **verificados** en producción (no
     inventados — extraídos del diagnóstico del 12-06-2026 y de la re-validación del
     28-06-2026, ver R6 de `requirements.md` para la evidencia completa):
     - Noticias, estudios/informes y páginas informativas de ONGs sobre el tema (no son la
       convocatoria en sí).
     - Licitaciones de contratación pública (compra de bienes/servicios), no subvenciones.
     - Proyectos YA financiados o ejecutados (ejecución de fondos, no oferta abierta).
     - Resultados que coinciden solo por un nombre propio o de lugar sin relación real con
       la convocatoria (p.ej. "El Salvador" como parroquia, club o municipio en España,
       cuando el objetivo es el país centroamericano).
     - Subvenciones o ayudas de ámbito nacional/doméstico ajenas a la cooperación
       internacional (p.ej. ayudas agrícolas domésticas que solo coinciden por un término
       como "soberanía alimentaria").
     - Convocatorias ya cerradas o con plazo vencido.
  5. Formato de salida: únicamente "SI" o "NO", en mayúsculas, sin explicación ni
     puntuación adicional — ninguna otra palabra.
  6. Los datos concretos (título + extracto del resultado) van en el **user prompt**, no en
     el system prompt (coherente con la Firma B de R1: instrucciones vs. datos separados).
- `classify_result(provider: LLMProvider, hit_title: str, hit_snippet: str) ->
  Literal["si", "no", "no_clasificado"]`: arma system (piezas 1-5, prompt cargado) + user
  (pieza 6, título + extracto), llama a `provider.complete(...)`, interpreta la respuesta
  (R6.3/R6.4).
- **T8 (integración, aditiva, Opción B — la marca vive en `llm/`):** una función en
  `llm/semantic_filter.py` (o un módulo `llm/filter_report.py` si conviene separarlo)
  recorre `report.opportunities` (las oportunidades ya construidas por el investigador en
  modo "calls") y aplica `classify_result` a **todas** ellas (Opción 1, sin enrutado por
  `result_type`). La función **devuelve una estructura nueva propia de la capa `llm/`**
  (p.ej. un `dataclass` o `dict` que mapea el identificador estable de cada `opportunity` a
  `"si"`/`"no"`/`"no_clasificado"`) — la forma exacta se decide al implementar T8. **NO
  muta `GrantOpportunity`, NO añade campos a `research/models.py`, NO toca `research/` en
  absoluto**: `result_type` (R6.5) y el resto de campos existentes quedan intactos, y
  tampoco hay cambios en `graph.py` ni `triage.py`. `research/models.py` se **lee**
  (`ResearchReport`, `GrantOpportunity`) pero no se modifica — el investigador sigue siendo
  un módulo portable ajeno al concepto de clasificación semántica LLM.
- **Modo "training" — no-op natural:** en modo "training", `report.opportunities` queda
  `[]` por diseño (`verify()` recolecta `resources` vía `TrainingCollector` y no construye
  `opportunities`; hallazgo documentado al cerrar la decisión #4/R23.3 en
  `investigador-v2`). El filtro, al recorrer `report.opportunities`, no tiene nada que
  clasificar en ese modo y devuelve la estructura vacía correspondiente — es el
  comportamiento correcto, no un fallo.

### R7 — Orquestación del filtro semántico (cableado al pipeline)

**Dónde:** `src/agente_ong/llm/health.py` (detección de disponibilidad) y
`src/agente_ong/llm/enrichment.py` (envoltorio `EnrichedReport`/`enrich_report`);
cableado en `src/agente_ong/ui/jobs.py` y aviso en `src/agente_ong/ui/app.py`.

- **Detección de LLM (`health.py`):** `is_ollama_available(base_url: str, timeout: float
  = 1.0) -> bool`. Sin excepciones: cualquier fallo de red al intentar contactar Ollama se
  traduce a `False`, nunca se propaga. Sustituye a `_preflight_ollama` de
  `scripts/prueba_filtro_semantico.py` (mismo propósito, ahora en código de producción
  reutilizable en vez de un script suelto).
- **`EnrichedReport` (`dataclass`, `enrichment.py`):** `base: ResearchReport` (el informe
  original, sin modificar — tipo importado de `research/models.py`),
  `discarded: list[GrantOpportunity]`, `unclassified: list[GrantOpportunity]`,
  `semantic_filter_applied: bool`. Dirección de la dependencia: `llm/` → `research/` (solo
  lectura de tipos), igual que ya hace hoy `filter_report.py` — no viola la Opción B (T8):
  `research/` sigue sin conocer la existencia del filtro semántico.
- **`enrich_report(report: ResearchReport, provider: LLMProvider | None) ->
  EnrichedReport`:**
  - `provider is None` (Ollama no disponible): devuelve `EnrichedReport(base=report,
    discarded=[], unclassified=[], semantic_filter_applied=False)`. `report` NO se clona
    en este camino — no hace falta, no se le quita nada. Degradación 100% silenciosa: el
    pipeline se comporta exactamente igual que antes de esta reapertura (R7.3).
  - `provider` disponible: llama a `classify_report(provider, report)` (T8, ya existe, no
    se toca) para obtener el `dict[id(opportunity), "si"|"no"|"no_clasificado"]`; separa
    `report.opportunities` en 3 listas según esa clasificación; construye un NUEVO
    `ResearchReport` con `dataclasses.replace(report, opportunities=kept)` (los demás
    campos — `ledger`, `failed_sources`, etc. — se preservan tal cual) y lo asigna a
    `base`; `discarded`/`unclassified` son las otras dos listas. El `report` de entrada
    nunca se muta (R7.2).
  - Un fallo de clasificación (`LLMError`) en una oportunidad concreta ya queda como
    `"no_clasificado"` en el dict que devuelve `classify_report` (comportamiento existente
    de T8, con `logger.warning` — se verifica y se reusa, no se reimplementa):
    `enrich_report` solo rutea esa entrada a `unclassified` como cualquier otra
    `"no_clasificado"` (R7.5).
- **Cableado (`ui/jobs.py`):** en `_run_job_inner`, tras `report =
  investigador.run(request, selected_ods)` y antes de persistir el resultado, se resuelve
  `provider` con `build_provider(LLMConfig.from_env())` (R3, alcance ampliado
  23-07-2026 — sustituye la construcción condicional `OllamaProvider(model=
  _OLLAMA_MODEL) if is_ollama_available() else None` hardcodeada hoy en `jobs.py:182`)
  y se llama `enrich_report(report, provider)`. Qué se persiste exactamente
  (`ProjectStore`/`report_to_dict` hoy solo conocen `ResearchReport`, no `EnrichedReport`)
  se decide en T11 — ver "Decisiones pendientes".
- **Aviso UI (`ui/app.py`):** mismo patrón que `_warn_missing_keys()` (commit `60c820b`),
  pero resuelto por `describe_llm_status(LLMConfig.from_env())` (R3/R7.7, alcance
  ampliado 23-07-2026) en vez de `is_ollama_available()` directamente: un
  `st.sidebar.warning(...)`/mensaje informativo con el texto que devuelva esa función,
  si no es `None`, al arrancar `main()`. El mensaje ya identifica el proveedor y el
  motivo (disabled, sin clave, no disponible, o default sin `LLM_PROVIDER` configurada)
  — `app.py` solo decide el estilo (warning vs. informativo) según el caso.

## Estrategia de tests con mock

Igual que `InMemoryStore` (`research/store/memory.py`) permite testear el investigador sin
tocar SQLite, un `FakeLLMProvider` (en `tests/llm/fakes.py`) implementa `LLMProvider` con
respuestas fijas e inyectables, sin llamar a proveedores reales ni gastar tokens:

- **Contrato del puerto (R1):** el fake y (con la capa LangChain mockeada) los tres
  adaptadores reales cumplen la misma forma de respuesta (`LLMResponse` con texto y
  tokens).
- **Errores y reintentos (R4):** el fake simula cada tipo de fallo (excepción de red,
  fallo de autenticación, sin respuesta) para verificar que se traduce al error propio
  correspondiente y que solo los fallos transitorios se reintentan.
- **Lectura de la respuesta del filtro (R6.3/R6.4):** el fake devuelve "SI" → `classify_result`
  da `"si"`; "NO" → `"no"`; una respuesta sucia (vacía, con explicación, minúsculas mal
  formadas más allá de lo normalizable) → `"no_clasificado"`.
- **Contador de tokens (R5):** el fake devuelve valores fijos de `input_tokens`/
  `output_tokens` y el test verifica que se propagan sin alterar.

**Explícitamente fuera de la cobertura con mock:** la calidad real de clasificación (si el
modelo distingue bien Tipo B/Tipo C de una convocatoria real) NO se testea con el fake —
depende del prompt y del modelo concretos, no de la tubería. Es una prueba manual aparte
con Ollama y/o Claude, análoga a la verificación en vivo de R17.3/R19.1/R23.6 de
`investigador-v2` pero sin fijarla como test automatizado de la suite.

## Orden de implementación y dependencias

Puerto (R1, independiente) → Errores/reintentos (R4, se apoya en el puerto para definir
dónde se atrapan las excepciones) → Adaptador Ollama (R2, primero por ser gratis y local,
sin clave) → Adaptadores Claude/OpenAI (R2, mismo contrato de test ya validado con Ollama)
→ Configuración (R3, una vez existen los tres adaptadores que la fábrica debe resolver) →
Carga del prompt del filtro (R6, preparación) → Filtro semántico (R6, usa el puerto + el
prompt cargado) → Integración con los resultados del investigador (R6, aditiva sobre
`ResearchReport`, sin tocar R20 de `investigador-v2`).

## Error Handling

- Cualquier excepción de la integración LangChain de un adaptador (timeout, error HTTP,
  respuesta vacía, clave inválida) se traduce a `LLMConnectionError`/`LLMAuthError`/
  `LLMNoResponseError` antes de propagarse — el consumidor (filtro, y los futuros chat/
  redactor) nunca ve una excepción de LangChain ni del SDK del proveedor.
- Un fallo del LLM al clasificar un resultado concreto en T8 no debe abortar el resto de la
  clasificación del informe: cada resultado se marca de forma independiente; un fallo
  aislado se refleja como "no_clasificado" (o se registra el error) sin tumbar el
  procesamiento de los demás resultados — mismo principio de aislamiento de fallos que
  `failed_sources` en el investigador.
- Respuesta del modelo no interpretable como SI/NO: nunca se fuerza a un valor por defecto
  (ni SI ni NO) — siempre "no_clasificado" (R6.4), coherente con el principio rector del
  producto de nunca inventar datos.

## Testing Strategy

- **R1:** `FakeLLMProvider` implementa el puerto; test de forma de `LLMResponse` (texto +
  tokens enteros no negativos).
- **R2:** test de contrato compartido (`test_provider_contract.py` o similar) parametrizado
  sobre los tres adaptadores, con la capa LangChain de cada uno mockeada (sin llamadas de
  red reales); Ollama sin clave configurada no falla en la construcción.
- **R3:** cambiar `LLM_PROVIDER` en el entorno resuelve un adaptador distinto vía
  `build_provider` sin cambios de código; claves ausentes para un proveedor no rompen la
  construcción de `LLMConfig` (solo fallarán al intentar usarlo, coherente con
  `ResearchConfig` y sus fuentes sin clave).
- **R4:** con el fake simulando cada excepción: se traduce al error propio correcto; los
  fallos transitorios se reintentan (contador de intentos verificable); `LLMAuthError` no
  se reintenta.
- **R5:** el fake fija tokens de entrada/salida; el test verifica que `LLMResponse` los
  expone sin transformarlos.
- **R6:** carga del prompt desde archivo (T6, contenido no vacío); `classify_result` con el
  fake devolviendo "SI"/"NO"/basura → `"si"`/`"no"`/`"no_clasificado"` (T7); integración
  (T8) recorriendo una lista de `GrantOpportunity` de prueba (`report.opportunities`
  simulado) → la estructura devuelta clasifica cada una, sin que `result_type` (R20 de
  `investigador-v2`) cambie de valor ni `research/models.py` se modifique; con
  `opportunities=[]` (caso modo "training") la función no falla y devuelve una estructura
  vacía.
- **R7:** `is_ollama_available` con Ollama mockeado (ping OK / conexión rechazada) → `True`/
  `False`, nunca excepción (T9); `enrich_report` sin provider → `base` intacto, buckets
  vacíos (T10); `enrich_report` con provider mock (3 oportunidades: "si"/"no"/
  "no_clasificado") → buckets correctos y `base.opportunities` solo con la "si" (T10);
  `enrich_report` con provider que lanza `LLMError` en una oportunidad → esa entrada en
  `unclassified` (T10); cableado en `jobs.py` con Ollama disponible/no disponible no rompe
  el flujo existente (T11).

## Decisiones pendientes (R7, abiertas)

- **Renderizado de `discarded`/`unclassified` en la UI (Markdown/HTML):** cómo pintar las
  2 secciones nuevas del `EnrichedReport` en `ui/report_view.py`/`ui/report_serde.py`.
  Fuera de alcance de esta reapertura (T9-T13 no tocan la UI de renderizado del informe,
  solo el aviso de disponibilidad de LLM).
- **Persistencia de `EnrichedReport`:** `ProjectStore.update_run_status` y
  `report_to_dict`/`report_from_dict` (`ui/report_serde.py`) hoy solo conocen
  `ResearchReport`. T11 (cableado en `jobs.py`) debe decidir: ¿se persiste solo `base`
  (comportamiento actual — `discarded`/`unclassified` se pierden al recargar la página) o
  se extiende la persistencia para guardar los 3 campos nuevos? No estaba en el alcance
  original de T9-T13 tal como se describieron; queda como decisión a tomar AL EMPEZAR T11,
  no al terminar.
