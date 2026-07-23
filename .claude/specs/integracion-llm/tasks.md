# Implementation Plan — integracion-llm (SPEC 2)

## Task Overview

Ocho tareas en orden de dependencia (cimientos hacia arriba): primero el puerto y su
contrato de errores (R1/R4), luego los adaptadores concretos empezando por el gratuito y
local (R2), después la configuración que los selecciona (R3), y por último el filtro
semántico completo — carga de prompt, lógica de clasificación e integración aditiva con
los resultados del investigador (R6). Cada tarea de código lleva su test y deja la suite en
verde. `R5` (contador de tokens) no tiene tarea propia: se cumple contractualmente en T1
(campos de `LLMResponse`) y se puebla en T3/T4 (adaptadores); sus tests viven en esas
tareas.

## Atomic Task Requirements

Cada tarea toca 1-3 archivos, es completable en 15-30 min, tiene un único resultado
testeable y especifica los archivos exactos.

## Tasks

### R1 — Puerto LLMProvider

- [x] 1. Puerto `LLMProvider` + `LLMResponse` en llm/provider.py
  - Files: src/agente_ong/llm/provider.py, tests/llm/fakes.py, tests/llm/test_provider.py
  - `LLMProvider(ABC)` con el método abstracto `complete(system: str, user: str) ->
    LLMResponse` (Firma B: system/user separados); `LLMResponse` (`dataclass`): `text: str`,
    `input_tokens: int`, `output_tokens: int`. Sin imports de LangChain ni de ningún SDK de
    proveedor en este módulo. `FakeLLMProvider` en `tests/llm/fakes.py` (respuestas y
    tokens inyectables, sin red) — mismo patrón que `InMemoryStore` para `ResearchStore`
  - Tests: `FakeLLMProvider` implementa el puerto; `complete(...)` devuelve un
    `LLMResponse` con `text` y tokens enteros no negativos
  - Purpose: contrato único e independiente de proveedor para todo consumidor de LLM
  - _Leverage: src/agente_ong/research/sources/base.py (SearchSource, mismo patrón ABC),
    src/agente_ong/research/store/memory.py (InMemoryStore, mismo patrón de fake)_
  - _Requirements: 1.1, 1.2, 1.3_

### R4 — Errores propios y reintentos

- [x] 2. Jerarquía de errores propios + reintentos en llm/errors.py
  - Files: src/agente_ong/llm/errors.py, tests/llm/test_errors.py
  - `LLMError` (base), `LLMConnectionError`, `LLMAuthError`, `LLMNoResponseError`.
    Reutilizar (importar o extraer a módulo compartido, decisión de esta tarea) el
    `with_retry` de `research/sources/base.py` para los fallos transitorios
    (`LLMConnectionError`); `LLMAuthError` nunca se reintenta
  - Tests: con `FakeLLMProvider` configurado para lanzar cada tipo de fallo: se traduce al
    error propio correspondiente; un fallo transitorio se reintenta (contador de intentos
    verificable con `sleep` inyectado, como en `test_with_retry` existente); `LLMAuthError`
    falla en el primer intento sin reintentar
  - Purpose: ningún consumidor ve una excepción cruda de LangChain o del SDK de proveedor
  - _Leverage: src/agente_ong/research/sources/base.py (with_retry, patrón de tests de
    reintentos con sleep inyectable)_
  - _Requirements: 4.1, 4.2, 4.3_

### R2 — Adaptadores Claude, OpenAI y Ollama

- [x] 3. Adaptador Ollama en llm/adapters/ollama.py
  - Files: src/agente_ong/llm/adapters/ollama.py, tests/llm/test_adapters.py,
    requirements.txt
  - PRIMERO: verificar EN VIVO (una llamada a un modelo Ollama local) el formato de
    respuesta y de `usage`/tokens de `langchain-ollama` antes de fijar el parseo (mismo
    método de verificación que R17.3/R19.1/R23.6 de `investigador-v2`). `OllamaProvider`
    implementa `LLMProvider`: construye el `ChatOllama` de LangChain, llama con
    system+user, traduce la respuesta a `LLMResponse` y las excepciones a los errores de
    R4. Sin clave de API requerida. Añadir `langchain-ollama` a `requirements.txt`
  - Tests: contrato del puerto contra `OllamaProvider` con la capa LangChain mockeada (sin
    red real); construcción sin clave no falla
  - Purpose: primer adaptador real, gratuito y local, para validar el contrato antes de
    pagar por los otros dos proveedores
  - _Leverage: src/agente_ong/llm/provider.py (LLMProvider, LLMResponse),
    src/agente_ong/llm/errors.py (tarea 2)_
  - _Requirements: 2.1, 2.3_

- [x] 4a. `OpenAICompatibleProvider` en `llm/adapters/openai_compatible.py` (reapertura
      21-07-2026, enfoque revisado: adaptador genérico, no uno específico de OpenAI)
  - Files: `src/agente_ong/llm/adapters/openai_compatible.py`,
    `tests/llm/test_adapters.py` (continúa de la tarea 3), `requirements.txt`
  - **Cambio de enfoque respecto al original de esta tarea:** en vez de un
    `OpenAIProvider` específico, se construyó `OpenAICompatibleProvider` — un único
    adaptador con `base_url`/`api_key`/`model` inyectables (los tres obligatorios, sin
    default) que sirve tanto para OpenAI como para cualquier proveedor que hable el
    mismo formato (verificado en la documentación oficial de DeepSeek:
    `https://api.deepseek.com`, endpoint `/chat/completions`, mismo formato de mensajes
    y de respuesta; la propia documentación de DeepSeek instruye a usar el SDK de
    `openai` sin modificar salvo `base_url`/`api_key`). `requirements.md` marcaba esto
    como "fuera de esta spec, candidato de BACKLOG" — corregido en este mismo cierre
    (ver ahí).
  - `ChatOpenAI` (`langchain-openai`), mismo contrato que `OllamaProvider`: implementa
    `LLMProvider`. Traducción de excepciones (jerarquía de `openai-python`
    `_exceptions.py`, confirmada leyendo el paquete instalado, NO verificada en vivo —
    sin clave de API disponible): `APIConnectionError` → `LLMConnectionError`
    (transitorio); `AuthenticationError` → `LLMAuthError` (caso nuevo, sin equivalente
    en Ollama); cualquier otro `OpenAIError` → `LLMNoResponseError`. Añadido
    `langchain-openai>=0.2` a `requirements.txt`
  - Tests: el mismo test de contrato de la tarea 3, parametrizado ahora sobre 2
    adaptadores (Ollama, OpenAI-compatible) — Claude queda para su propia sub-tarea (4b,
    ver abajo); 3 tests específicos de traducción de excepciones (conexión, auth, otro
    error), mockeando `ChatOpenAI` — sin llamada real, sin `DEEPSEEK_API_KEY`
  - Purpose: desbloquear un proveedor de pago barato (DeepSeek) sin comprometerse a un
    único proveedor concreto — cambiar de OpenAI a DeepSeek a otro compatible es solo
    cambiar `base_url`
  - _Leverage: src/agente_ong/llm/adapters/ollama.py (mismo molde de traducción de
    excepciones y parseo de `usage_metadata`), src/agente_ong/research/config.py (patrón
    de gestión de claves a reutilizar cuando T5 lea `DEEPSEEK_API_KEY` del entorno — no
    se adelanta esa tarea aquí, el adaptador se construye con argumentos explícitos)_
  - _Requirements: 2.1, 2.2 (parcial — ver 4b para Claude)_
  - **Pendiente antes de confiar en esto en producción:** verificación EN VIVO del
    formato de `usage_metadata`/excepciones contra una respuesta real de DeepSeek, en
    cuanto exista `DEEPSEEK_API_KEY` (mismo principio que T3 aplicó a Ollama). No
    bloquea el uso con mocks/tests.

- [ ] 4b. [APLAZADA — pendiente de clave Anthropic] Adaptador Claude en
      llm/adapters/claude.py
  - Files: src/agente_ong/llm/adapters/claude.py, tests/llm/test_adapters.py
  - Sin cambios respecto al plan original: `ClaudeProvider` (`ChatAnthropic`,
    `langchain-anthropic`), mismo contrato que `OllamaProvider`/
    `OpenAICompatibleProvider`. PRIMERO verificar EN VIVO el formato de
    `usage_metadata`/tokens de `langchain-anthropic` (difiere de Ollama/OpenAI) antes de
    fijar el parseo. No es "OpenAI-compatible" (protocolo de mensajes distinto de
    Anthropic), por eso no se resolvió junto con 4a
  - Tests: añadir Claude a la misma lista `ADAPTERS` parametrizada de
    `tests/llm/test_adapters.py`
  - Purpose: completar los tres proveedores intercambiables que pedía R2.1 original
  - _Leverage: src/agente_ong/llm/adapters/ollama.py, src/agente_ong/llm/adapters/openai_compatible.py
    (mismo molde)_
  - _Requirements: 2.1, 2.2_

### R3 — Configuración

*Reapertura 23-07-2026 (alcance en `requirements.md` R3/R7, commit `58ccd1f`; diseño en
`design.md`, commit `9e80d6b`). La tarea 5 original (aplazada por falta de claves
Claude/OpenAI) se divide en seis subtareas atómicas — T5a-T5f — para desbloquear
`LLMConfig`/`build_provider` con selección multi-proveedor por entorno
(`ollama`/`deepseek`/`openai`/`disabled`), sin esperar a Claude (T4b sigue aplazada).
Orden de ejecución: T5a → T5b → T5c → T5d → T5e → T5f (cada una es un commit propio,
`feat:`/`test:`).*

- [ ] 5a. `LLMConfig` + `from_env()` + presets internos en `llm/config.py`
  - Files: `src/agente_ong/llm/config.py` (nuevo), `tests/llm/test_config.py` (nuevo)
  - `LLMConfig` (`dataclass`): `provider: Literal["ollama", "deepseek", "openai",
    "disabled"]`, `provider_explicit: bool`, `temperature: float = 0.0`,
    `deepseek_api_key: str | None = None`, `openai_api_key: str | None = None` (Ollama
    sin campo de clave). `LLMConfig.from_env()`: `load_dotenv(env_path,
    override=False)` (mismo patrón que `ResearchConfig.from_env()`, ajustando el número
    de `parents[...]` según la profundidad real del archivo); lee `LLM_PROVIDER` (si
    ausente: `provider="ollama"`, `provider_explicit=False`; si presente, a cualquier
    valor: `provider_explicit=True`), `LLM_TEMPERATURE`, `DEEPSEEK_API_KEY`,
    `OPENAI_API_KEY` — lee TODAS las claves presentes, sin validar cuál hace falta (esa
    comprobación es de T5b). Dos presets privados: `_PAID_PROVIDER_PRESETS:
    dict[str, tuple[str, str]]` (`base_url`, `model` para `deepseek`/`openai`; valores
    exactos a fijar en esta tarea, sin verificación en vivo — ver nota de T5b) y
    `_OLLAMA_MODEL_PRESET = "qwen2.5:7b"` (mismo valor que hoy `ui/jobs.py::_OLLAMA_MODEL`,
    verificado en vivo en T3; T5d retira el duplicado de `jobs.py`)
  - Tests: `from_env()` sin `LLM_PROVIDER` → `provider="ollama"`,
    `provider_explicit=False`; con `LLM_PROVIDER=deepseek` → `provider="deepseek"`,
    `provider_explicit=True`; con un valor no reconocido (p.ej. `LLM_PROVIDER=grok`) →
    se guarda tal cual, `provider_explicit=True` (validar valores reconocidos es de
    `build_provider`, T5b, no de `from_env`); claves ausentes
    (`DEEPSEEK_API_KEY`/`OPENAI_API_KEY` no definidas) no rompen la construcción, quedan
    `None`; `LLM_TEMPERATURE` no definida cae en el default `0.0`; una variable ya
    presente en `os.environ` gana sobre el `.env` (`override=False`, mismo contrato que
    `ResearchConfig`)
  - Purpose: base de configuración multi-proveedor sin tocar código para cambiar de
    proveedor (R3.1, R3.4); ninguna clave se hardcodea (R3.3); modelo/`base_url` de pago
    quedan fuera del entorno, como presets internos (R3.5)
  - _Leverage: `src/agente_ong/research/config.py` (patrón `dataclass` + `from_env()` +
    `load_dotenv(env_path, override=False)`, líneas 124-169), `src/agente_ong/ui/jobs.py`
    (`_OLLAMA_MODEL`, línea 44, valor a preservar como preset)_
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_
  - Done: `pytest tests/llm/test_config.py -q` en verde con los casos descritos;
    `LLMConfig`/`from_env()` no importan ningún adaptador de `llm/adapters/` (solo T5b
    los conoce)

- [ ] 5b. `build_provider()` en `llm/config.py`
  - Files: `src/agente_ong/llm/config.py` (continúa de T5a), `tests/llm/test_config.py`
    (continúa de T5a)
  - `build_provider(config: LLMConfig) -> LLMProvider | None`: sin excepciones, resuelve
    las 5 ramas — `"disabled"` → `None`; `"ollama"` → `None` si `is_ollama_available()`
    es `False`, si no `OllamaProvider(model=_OLLAMA_MODEL_PRESET)`;
    `"deepseek"`/`"openai"` → `None` si falta la clave correspondiente, si no
    `OpenAICompatibleProvider` con el preset de `_PAID_PROVIDER_PRESETS[config.provider]`
    (`base_url`, `model`) y la clave leída, más `temperature=config.temperature`;
    cualquier valor de `provider` no reconocido → `None`. Es el único punto del código,
    fuera de los adaptadores, que conoce los cuatro nombres de proveedor (R3, "Dónde")
  - Tests: las 5 ramas, con `is_ollama_available` mockeado (sin red real) y las clases
    `OllamaProvider`/`OpenAICompatibleProvider` mockeadas (verificar argumentos de
    construcción, sin llamar a LangChain real): `disabled` → `None`; `ollama`
    disponible → `OllamaProvider` con el preset; `ollama` no disponible → `None`;
    `deepseek` con clave → `OpenAICompatibleProvider` con el preset de `deepseek`;
    `deepseek` sin clave → `None`; `openai` con/sin clave → análogo; `provider="grok"`
    (no reconocido) → `None`, sin excepción
  - Purpose: fábrica única del fallback silencioso completo (R7.3): `disabled`,
    proveedor sin clave y proveedor no disponible se comportan todos igual para el
    consumidor — `provider=None`, degradación 100% silenciosa
  - _Leverage: `src/agente_ong/llm/health.py::is_ollama_available` (T9, sin tocar),
    `src/agente_ong/llm/adapters/ollama.py::OllamaProvider`,
    `src/agente_ong/llm/adapters/openai_compatible.py::OpenAICompatibleProvider` (T3,
    T4a, sin tocar)_
  - _Requirements: 3.1, 3.4, 7.3_
  - Done: `pytest tests/llm/test_config.py -q` en verde con las 7 combinaciones (5 ramas
    + no reconocido + verificación de que ninguna rama propaga una excepción cruda)

- [ ] 5c. `describe_llm_status()` en `llm/config.py`
  - Files: `src/agente_ong/llm/config.py` (continúa de T5b), `tests/llm/test_config.py`
    (continúa de T5b)
  - `describe_llm_status(config: LLMConfig) -> tuple[LLMProvider | None, str | None]`:
    envuelve `build_provider` (T5b, sin reimplementar la resolución) y añade el mensaje
    legible. Cinco combinaciones: `disabled` → "filtro desactivado por configuración";
    proveedor de pago sin clave → nombra proveedor y variable ausente (p.ej. "`deepseek`
    configurado pero falta `DEEPSEEK_API_KEY`"); proveedor inalcanzable → nombra el
    proveedor (p.ej. "`ollama` configurado pero no responde"); proveedor disponible con
    `provider_explicit=True` → mensaje `None` (sin aviso); `provider_explicit=False`
    (sin `LLM_PROVIDER` en el entorno) → mensaje SIEMPRE presente ("`LLM_PROVIDER` no
    definida, usando `ollama` por defecto"), combinado con el motivo si además `ollama`
    no responde — única combinación con mensaje pese a `provider` disponible
  - Tests: las 5 combinaciones descritas en `design.md` (bullet "Healthcheck del
    sidebar"), verificando el texto exacto de cada mensaje y que el `LLMProvider`
    devuelto coincide con el de `build_provider` para el mismo `config` (misma
    resolución, no una lógica divergente)
  - Purpose: el sidebar (T5d) necesita el motivo del `None`, no solo el resultado — base
    de R7.7
  - _Leverage: `build_provider` (T5b, esta misma tarea la envuelve sin duplicar la
    resolución)_
  - _Requirements: 7.6, 7.7_
  - Done: `pytest tests/llm/test_config.py -q` en verde con los 5 casos; el mensaje de
    cada combinación coincide literalmente con el descrito en `design.md`

- [ ] 5d. Cableado en `ui/jobs.py` y `ui/app.py`
  - Files: `src/agente_ong/ui/jobs.py`, `src/agente_ong/ui/app.py`,
    `tests/ui/test_jobs.py`, `tests/ui/test_app_smoke.py`
  - `jobs.py`: en `_run_job_inner`, sustituir `OllamaProvider(model=_OLLAMA_MODEL) if
    is_ollama_available() else None` (línea 182) por `build_provider(LLMConfig.
    from_env())`; retirar `_OLLAMA_MODEL` (línea 44, duplicado ya cubierto por
    `_OLLAMA_MODEL_PRESET` de T5a) y el import de `OllamaProvider` si queda huérfano.
    `app.py`: `_warn_llm_unavailable` (líneas 132-146) pasa a resolver `provider,
    message = describe_llm_status(LLMConfig.from_env())`; si `message` no es `None`,
    `st.sidebar.warning(message)` para los casos de alarma (disabled/sin clave/no
    disponible) — decidir en esta tarea si el caso informativo puro
    (`provider_explicit=False` con proveedor disponible, T5c) usa el mismo
    `st.sidebar.warning` o un `st.sidebar.info` distinto; `_cached_ollama_available`
    (líneas 123-129) se sustituye por una versión cacheada equivalente de
    `describe_llm_status` (mismo TTL 30s, mismo motivo: no gastar 1s de HTTP en cada
    rerun)
  - Tests: con `LLMConfig`/`build_provider` mockeados o con variables de entorno de
    test: `jobs.py` inyecta el `LLMProvider` esperado según `LLM_PROVIDER` (3 proveedores
    reales + `disabled`); smoke de `app.py` con cada una de las 5 combinaciones de
    `describe_llm_status` mockeado, verificando que el sidebar muestra (o no) el mensaje
    esperado
  - Purpose: primer punto real donde T5 sustituye el hardcodeo — cierre de R3.4/R7.3/
    R7.6/R7.7 en producción
  - _Leverage: `src/agente_ong/llm/config.py` (T5a-T5c), patrón de
    `_cached_ollama_available`/`_warn_llm_unavailable` ya existente en `app.py:123-146`_
  - _Requirements: 3.4, 7.3, 7.6, 7.7_
  - Done: `pytest tests/ui/test_jobs.py tests/ui/test_app_smoke.py -q` en verde; `grep
    -rn "_OLLAMA_MODEL\b" src/agente_ong/ui/jobs.py` sin resultados (confirma retirada
    del duplicado)

- [ ] 5e. Verificar sincronización `st.secrets` → `os.environ` para las claves nuevas
  - Files: `src/agente_ong/ui/app.py` (verificación, sin cambio esperado),
    `tests/ui/test_app_smoke.py` (o test nuevo si conviene aislarlo)
  - `_sync_streamlit_secrets_to_env` (`app.py:71-91`) copia CUALQUIER clave presente en
    `st.secrets` a `os.environ` sin lista blanca (ya verificado por lectura de código en
    esta sesión) — confirmar con test que `DEEPSEEK_API_KEY`/`OPENAI_API_KEY` entran por
    el mismo mecanismo que `TAVILY_API_KEY`, sin tocar la función. Si se confirma que no
    hace falta código nuevo, esta tarea es solo el test que lo prueba
  - Tests: con `st.secrets` simulado conteniendo `DEEPSEEK_API_KEY`: tras
    `_sync_streamlit_secrets_to_env()`, `os.environ["DEEPSEEK_API_KEY"]` queda poblada;
    una variable ya presente en `os.environ` no se sobrescribe (contrato `if key not in
    os.environ`, línea 88)
  - Purpose: cerrar R3.6 con evidencia, no solo por lectura de código
  - _Leverage: `src/agente_ong/ui/app.py::_sync_streamlit_secrets_to_env` (líneas
    71-91, sin tocar si la verificación confirma que ya cubre el caso)_
  - _Requirements: 3.6_
  - Done: test nuevo o extendido en verde; si `_sync_streamlit_secrets_to_env`
    necesitara un cambio (contra lo esperado), documentarlo en el commit — no se prevé,
    pero no se fuerza el resultado

- [ ] 5f. Documentar las variables nuevas en `.env.example`
  - Files: `.env.example`
  - Añadir, comentadas (mismo estilo que las variables opcionales ya presentes, líneas
    17-56): `LLM_PROVIDER` (con los 4 valores válidos y el default `ollama` si se
    omite), `LLM_TEMPERATURE`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`. Nota explícita de
    que NO existe `LLM_BASE_URL`/`LLM_MODEL` — el `base_url` y el modelo de los
    proveedores de pago son presets internos del código, no configurables aquí
  - Tests: ninguno — archivo de documentación, no código
  - Purpose: que quien clone el repo sepa qué variables de LLM existen sin leer
    `llm/config.py`
  - _Leverage: `.env.example` (formato ya establecido: comentario explicativo + línea
    comentada con el nombre y un valor de ejemplo)_
  - _Requirements: 3.3, 3.5, 3.6_
  - Done: `.env.example` incluye las 4 variables nuevas comentadas y la nota sobre
    `LLM_BASE_URL`/`LLM_MODEL`; ningún valor de ejemplo funcional (mismo principio que
    las entradas existentes, `tvly-tu_clave_aqui`/`fc-tu_clave_aqui`)

### R6 — Filtro semántico (Opción 1)

- [x] 6. Prompt del filtro en archivo + cargador en llm/prompts/
  - Files: src/agente_ong/llm/prompts/semantic_filter.md, src/agente_ong/llm/prompt_loader.py,
    tests/llm/test_prompt_loader.py
  - Redactar `semantic_filter.md` con las 5 primeras piezas del prompt (rol, pregunta
    exacta, qué cuenta como SÍ, qué cuenta como NO —con los falsos positivos verificados:
    noticias/estudios/páginas de ONGs, licitaciones, proyectos ya financiados, resultados
    que casan solo por nombre propio/lugar, subvenciones nacionales ajenas a cooperación
    internacional, convocatorias cerradas—, formato de salida SI/NO estricto). `load_prompt
    (name: str) -> str` en `prompt_loader.py`: lee el `.md` correspondiente de `llm/prompts/`
  - Tests: `load_prompt("semantic_filter")` devuelve contenido no vacío que incluye la
    pregunta SI/NO y las instrucciones de formato de salida
  - Purpose: el prompt es editable sin tocar código Python (patrón "skill", reutilizado por
    el agente redactor de SPEC 4)
  - _Requirements: 6.1_

- [x] 7. classify_result en llm/semantic_filter.py
  - Files: src/agente_ong/llm/semantic_filter.py, tests/llm/test_semantic_filter.py
  - `classify_result(provider: LLMProvider, title: str, snippet: str) -> Literal["si",
    "no", "no_clasificado"]`: arma el system prompt (cargado con `load_prompt`, tarea 6) y
    el user prompt (título + extracto del resultado, pieza 6 del diseño); llama a
    `provider.complete(system, user)`; normaliza la respuesta (`strip().upper()`) y la
    interpreta: "SI" exacto → `"si"`, "NO" exacto → `"no"`, cualquier otra cosa →
    `"no_clasificado"` (nunca por defecto SI o NO)
  - Tests: con `FakeLLMProvider` devolviendo "SI" → `"si"`; "NO" → `"no"`; respuesta vacía,
    con explicación, o en minúsculas mal formadas más allá de lo normalizable → `
    "no_clasificado"`; el user prompt enviado contiene el título y el extracto del
    resultado de prueba
  - Purpose: traducción fiable de la respuesta del LLM a un booleano (o "no clasificado"),
    válida para los tres proveedores por igual
  - _Leverage: src/agente_ong/llm/provider.py (LLMProvider), src/agente_ong/llm/prompt_loader.py
    (load_prompt, tarea 6), tests/llm/fakes.py (FakeLLMProvider)_
  - _Requirements: 6.1, 6.3, 6.4_

- [x] 8. Integración del filtro con los resultados del investigador (Opción B: marca en `llm/`)
  - Files: src/agente_ong/llm/semantic_filter.py (continúa de la tarea 7),
    tests/llm/test_semantic_filter.py
  - Función que recorre `report.opportunities` (las oportunidades ya construidas por el
    investigador en modo "calls") y aplica `classify_result` a **todas** ellas (Opción 1,
    sin enrutado por `result_type`), devolviendo una **estructura nueva propia de `llm/`**
    (p.ej. `dataclass`/`dict` que mapea el identificador estable de cada `opportunity` a
    `"si"`/`"no"`/`"no_clasificado"`; forma exacta a decidir en esta tarea). NO muta
    `GrantOpportunity`, NO añade campos a `research/models.py`, NO se toca `research/` en
    absoluto: `result_type` queda intacto y `graph.py`/`triage.py` no se tocan. En modo
    "training", `report.opportunities` es `[]` por diseño (ver R23.3/decisión #4 de
    `investigador-v2`): el filtro es un no-op natural en ese modo. Un fallo de
    clasificación en una oportunidad no aborta el resto (aislamiento, coherente con
    `failed_sources`)
  - Tests: con `FakeLLMProvider` y una lista de `GrantOpportunity` de prueba con distintas
    respuestas fijas por resultado: la estructura devuelta clasifica cada una (si/no/
    no_clasificado); `result_type` de cada resultado permanece intacto tras el filtrado; un
    resultado cuya clasificación falla (excepción del fake) no impide clasificar el resto;
    con `opportunities=[]` (caso modo "training") el filtro no falla y devuelve una
    estructura vacía
  - Purpose: primer consumidor real de la infraestructura LLM, aditivo sobre el
    investigador, sin tocar R20 ni `research/`
  - _Leverage: src/agente_ong/llm/semantic_filter.py (classify_result, tarea 7),
    src/agente_ong/research/models.py (ResearchReport, GrantOpportunity — se LEEN, no se
    modifican)_
  - _Requirements: 6.2, 6.5_

### R7 — Orquestación del filtro semántico (cableado al pipeline)

*Reapertura 09-07-2026. Opción C: `research/` queda intacto (Opción B/decisión #8 de T8 sin
tocar); la orquestación vive entera en `llm/`. Orden de ejecución estricto: 9 → 10 → 11 →
12 → 13. Cada tarea, commit + push.*

- [x] 9. `is_ollama_available()` en llm/health.py
  - Files: src/agente_ong/llm/health.py, tests/llm/test_health.py
  - `is_ollama_available(base_url: str = DEFAULT_BASE_URL, timeout: float = 1.0) -> bool`:
    intenta un ping mínimo contra el servidor Ollama; captura CUALQUIER excepción de
    red/timeout y devuelve `False` — nunca propaga. Sustituye a `_preflight_ollama` de
    `scripts/prueba_filtro_semantico.py` (mismo propósito, ahora reutilizable en código de
    producción)
  - Tests: con Ollama mockeado respondiendo OK → `True`; con conexión rechazada/timeout →
    `False`, sin excepción
  - Purpose: saber si hay LLM disponible sin arriesgar una excepción cruda en el arranque
    de la UI ni en el cableado de `jobs.py`
  - _Leverage: src/agente_ong/llm/adapters/ollama.py (DEFAULT_BASE_URL)_
  - _Requirements: 7.1_

- [x] 10. `EnrichedReport` + `enrich_report()` en llm/enrichment.py
  - Files: src/agente_ong/llm/enrichment.py, tests/llm/test_enrichment.py
  - `EnrichedReport` (`dataclass`): `base: ResearchReport`, `discarded:
    list[GrantOpportunity]`, `unclassified: list[GrantOpportunity]`,
    `semantic_filter_applied: bool`. `enrich_report(report: ResearchReport, provider:
    LLMProvider | None) -> EnrichedReport`: sin provider, pasa `report` intacto como
    `base` con buckets vacíos y `semantic_filter_applied=False`; con provider, usa
    `classify_report` (T8, ya existe) para separar kept/discarded/unclassified y construye
    `base` con `dataclasses.replace(report, opportunities=kept)` — el `report` de entrada
    nunca se muta
  - Tests: (a) provider=None → `base` es el mismo report, buckets vacíos,
    `semantic_filter_applied=False`; (b) provider mock con 3 oportunidades
    ("si"/"no"/"no_clasificado") → buckets correctos, `base.opportunities` contiene solo
    la "si"; (c) provider mock que lanza `LLMError` en una oportunidad → esa entrada
    termina en `unclassified`
  - Purpose: capa de orquestación aditiva que enriquece un `ResearchReport` sin que
    `research/` conozca la existencia del filtro semántico (Opción B, decisión #8 de T8,
    intacta)
  - _Leverage: src/agente_ong/llm/filter_report.py (classify_report, T8),
    src/agente_ong/research/models.py (ResearchReport, GrantOpportunity — se LEEN, no se
    modifican)_
  - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [x] 11. Cableado en ui/jobs.py
  - Files: src/agente_ong/ui/jobs.py, tests/ui/test_jobs.py
  - En `_run_job_inner`, tras `investigador.run(...)` y antes de persistir: resolver
    `provider` (construir `OllamaProvider` solo si `is_ollama_available()` es `True`, si
    no `None`) y llamar `enrich_report(report, provider)`. Decidir en esta tarea qué se
    persiste (ver "Decisiones pendientes" de `design.md`: solo `base`, o los 3 campos
    nuevos también)
  - Tests: con Ollama disponible (mock) y con Ollama no disponible — ambos casos no rompen
    el flujo existente de jobs
  - Purpose: primer punto real donde el filtro semántico se ejecuta dentro del pipeline de
    producción
  - _Leverage: src/agente_ong/llm/health.py (tarea 9), src/agente_ong/llm/enrichment.py
    (tarea 10), src/agente_ong/llm/adapters/ollama.py (OllamaProvider)_
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 12. Warning en sidebar si no hay LLM disponible
  - Files: src/agente_ong/ui/app.py
  - Mismo patrón que `_warn_missing_keys()` (commit `60c820b`): si
    `is_ollama_available()` es `False` al arrancar `main()`, `st.sidebar.warning(...)`
    persistente explicando que la investigación seguirá funcionando sin clasificar
  - Tests: manual (captura de pantalla) + automatizados en tests/ui/test_app_smoke.py
    (con/sin Ollama disponible, mockeando `agente_ong.llm.health.is_ollama_available`)
  - Purpose: visibilidad — el usuario sabe por qué no hay clasificación semántica, en vez
    de descubrirlo por ausencia silenciosa (mismo principio que motivó el arreglo del bug
    de `.env`, commit `60c820b`)
  - _Leverage: src/agente_ong/ui/app.py (_warn_missing_keys, commit 60c820b)_
  - _Requirements: 7.6_

- [x] 13. Verificación empírica end-to-end (caso de prueba del 05-07)
  - Files: ninguno (prueba manual)
  - Sin Ollama corriendo: mismo resultado que antes de esta reapertura (74 convocatorias,
    22 documentos informativos) + warning visible en sidebar; `EnrichedReport` con buckets
    vacíos y `semantic_filter_applied=False`. Con Ollama corriendo: N kept en
    `base.opportunities`, M discarded (validar que incluye el ruido de Canarias de la
    decisión #14 y ruido identificable de Tavily — linguee/instagram/flickr) + K
    unclassified
  - Tests: manual; anexar resultado al checkpoint de la próxima sesión
  - Purpose: cerrar la reapertura con evidencia empírica, no solo con tests unitarios —
    mismo principio que el cierre de R25 de `investigador-v2`
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
