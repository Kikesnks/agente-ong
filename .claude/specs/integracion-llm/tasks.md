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

- [ ] 4. Adaptadores Claude y OpenAI en llm/adapters/claude.py y openai.py
  - Files: src/agente_ong/llm/adapters/claude.py, src/agente_ong/llm/adapters/openai.py,
    tests/llm/test_adapters.py (continúa de la tarea 3), requirements.txt
  - PRIMERO: verificar EN VIVO el formato de `usage_metadata`/tokens de
    `langchain-anthropic` y `langchain-openai` (difiere de Ollama) antes de fijar el
    parseo. `ClaudeProvider` (`ChatAnthropic`) y `OpenAIProvider` (`ChatOpenAI`), mismo
    contrato que `OllamaProvider`: implementan `LLMProvider`, traducen excepciones a los
    errores de R4. Añadir `langchain-anthropic` y `langchain-openai` a `requirements.txt`
  - Tests: el MISMO test de contrato de la tarea 3, parametrizado sobre los tres
    adaptadores (Ollama, Claude, OpenAI), con la capa LangChain de cada uno mockeada;
    verifica que los tres son intercambiables (misma forma de `LLMResponse`)
  - Purpose: completar los tres proveedores con un contrato de test único y compartido
  - _Leverage: src/agente_ong/llm/adapters/ollama.py (tarea 3, mismo molde),
    tests/llm/test_adapters.py (test de contrato parametrizable)_
  - _Requirements: 2.1, 2.2_

### R3 — Configuración

- [ ] 5. LLMConfig + build_provider en llm/config.py
  - Files: src/agente_ong/llm/config.py, tests/llm/test_config.py
  - `LLMConfig` (`dataclass`): `provider: Literal["claude", "openai", "ollama"]`, `model:
    str`, `temperature: float = 0.0`, `anthropic_api_key`/`openai_api_key: str | None`.
    `LLMConfig.from_env()` lee `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TEMPERATURE`,
    `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (mismo patrón que `ResearchConfig.from_env()`).
    `build_provider(config: LLMConfig) -> LLMProvider`: resuelve el adaptador según
    `config.provider`
  - Tests: cambiar `LLM_PROVIDER` en el entorno hace que `build_provider` devuelva un
    adaptador distinto sin tocar código; claves ausentes no rompen la construcción de
    `LLMConfig` (solo fallarían al usar el proveedor); `from_env()` con variables no
    definidas cae en los defaults
  - Purpose: cambiar de proveedor es solo configuración (R3.4); las claves se leen del
    entorno, nunca hardcodeadas
  - _Leverage: src/agente_ong/research/config.py (patrón dataclass + from_env + _env_int),
    src/agente_ong/llm/adapters/ (los tres adaptadores de las tareas 3-4)_
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

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
