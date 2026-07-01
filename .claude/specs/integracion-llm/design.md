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
`research/config.py` (`dataclass` + `from_env()`).

- `LLMConfig` (`dataclass`): `provider: Literal["claude", "openai", "ollama"]`,
  `model: str`, `temperature: float = 0.0` (determinismo por defecto, apropiado para el
  filtro SI/NO de R6), claves de API por proveedor (`anthropic_api_key`, `openai_api_key`;
  Ollama sin clave).
- `LLMConfig.from_env()` lee `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TEMPERATURE`,
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (mismas convenciones de nombre que
  `ResearchConfig.from_env()` en `research/config.py`: prefijo del dominio + `_env_int`/
  variante float reutilizable).
- Una función `build_provider(config: LLMConfig) -> LLMProvider` (fábrica simple) resuelve
  qué adaptador instanciar según `config.provider` — es el único punto del código, fuera de
  los propios adaptadores, que conoce los tres nombres de proveedor; los consumidores
  (filtro, y en el futuro chat/redactor) reciben ya un `LLMProvider` inyectado y nunca
  llaman a `build_provider` ellos mismos salvo en el punto de composición (wiring de la
  UI/CLI), igual que `investigador.py` construye las `SearchSource` concretas.

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
- **T8 (integración, aditiva):** una función en `llm/semantic_filter.py` (o un módulo
  `llm/filter_report.py` si conviene separarlo) recorre `SearchHit`/`GrantOpportunity` de
  un `ResearchReport` ya construido por el investigador y anota el resultado de
  `classify_result` en cada uno — sin modificar `result_type` (R6.5) ni ningún otro campo
  existente. Al ser aditivo, no requiere cambios en `graph.py` ni en el modelo de datos de
  `research/models.py` más allá de un campo nuevo opcional para guardar la marca del
  filtro (nombre exacto y ubicación del campo se deciden en T8, retrocompatible con
  default "no_clasificado" o `None`, siguiendo el mismo patrón retrocompatible que
  `result_type` en R20 de `investigador-v2`).

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
  (T8) con una lista de resultados simulados (`SearchHit`/`GrantOpportunity` de prueba) →
  cada uno queda marcado, sin que `result_type` (R20 de `investigador-v2`) cambie de valor.
