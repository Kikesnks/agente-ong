# Spec integracion-llm — requirements.md (SPEC 2)

*Fecha: 01-07-2026. Origen: roadmap `Contexto_para_mi/roadmap_specs_agente-ong_v4_22-06-2026.md`
("SPEC 2: Integración LLM") + evidencia de falsos positivos del diagnóstico del 12-06-2026
(`investigador-v2`) y de la re-validación T19/R21 del 28-06-2026.*

## Introducción

SPEC 2 construye la abstracción multi-proveedor de LLM que el resto del roadmap (chat de
proyecto, agente redactor, generación de `query_terms`, refinado de `search_context`)
necesita como base, y la valida con su primer consumidor real: un **filtro semántico
mínimo** sobre los resultados del investigador.

Alcance del filtro (**Opción 1**, decisión de producto): el LLM clasifica **TODOS** los
resultados de una investigación con una única pregunta SI/NO. No hay enrutado heurístico
por `result_type` ni extracción estructurada de campos — eso queda para specs
posteriores (redactor, chat) una vez validada la infraestructura LLM en producción.

**Fuera de alcance de esta spec:**
- Streaming de respuesta (lo necesitará el chat de SPEC 3; se diseña allí).
- Presupuesto/límite de tokens (contador sí, control de coste no — backlog v1.1).
- UI de gestión de claves API (SPEC 6; aquí las claves solo se leen del entorno).
- Adaptador genérico OpenAI-compatible (Grok, DeepSeek, etc.) — candidato de BACKLOG,
  fuera de esta spec.
- Enrutado heurístico o extracción estructurada de campos vía LLM — posterior a validar
  el filtro mínimo en producción.

**No se modifica investigador-v2:** el filtro es una capa NUEVA por encima del módulo
`research/`. En particular, `R20` (pre-clasificación heurística `result_type`) de
`investigador-v2` no se toca — el filtro semántico es aditivo, no la sustituye.

### Nota de numeración

Cada spec bajo `.claude/specs/` numera sus requisitos `R1..` de forma **independiente**
(confirmado por `streamlit`, que reutiliza `R14`/`R15` para las extensiones UI-34/UI-35 sin
colisionar con los `R14`/`R15`, de contenido distinto, de `investigador-v2`). Esta spec seguirá
la misma convención: sus requisitos empiezan en `R1` y son locales a `integracion-llm`;
cualquier referencia a requisitos de otra spec se cualifica explícitamente con su nombre
(p.ej. "R20 de investigador-v2").

---

## R1 — Puerto `LLMProvider`

**Evidencia:** todos los consumidores futuros (filtro semántico aquí; chat, redactor y
refinado de queries en specs posteriores) necesitan hablar con un LLM sin acoplarse a un
proveedor concreto (`tech.md`: "el código abstrae el proveedor").

Criterios de aceptación:
- 1.1 El puerto expone una única operación que recibe un *system prompt* y un *user
  prompt* por separado (no un prompt único concatenado) y devuelve una respuesta con el
  texto generado y el recuento de tokens de entrada y de salida.
- 1.2 Ningún código del núcleo (filtro semántico, y en el futuro chat/redactor) importa
  LangChain ni ningún SDK de proveedor: solo conoce el puerto.
- 1.3 El puerto es una interfaz (patrón Ports & Adapters, igual que `SearchSource` en
  `research/sources/base.py` y `ResearchStore` en `research/store/base.py`): cualquier
  implementación que la satisfaga es intercambiable sin tocar el código consumidor.

## R2 — Adaptadores Claude, OpenAI y Ollama

**Evidencia:** `tech.md` exige alternar entre Claude, OpenAI y otros sin reescribir la
lógica de agentes; `Ollama` es el proveedor local/gratuito elegido para desarrollo y
pruebas sin coste.

Criterios de aceptación:
- 2.1 Existen tres adaptadores — Claude (Anthropic), OpenAI y Ollama — que implementan el
  puerto `LLMProvider` usando LangChain internamente.
- 2.2 Los tres adaptadores son intercambiables entre sí sin cambiar el código consumidor:
  cambiar de proveedor es sustituir la instancia inyectada, nunca una rama `if` en el
  código de negocio.
- 2.3 El adaptador Ollama no requiere clave de API (proveedor local).
- 2.4 Un adaptador genérico OpenAI-compatible (para Grok, DeepSeek u otros proveedores con
  API compatible con OpenAI) queda **fuera de esta spec**, registrado como candidato de
  BACKLOG v1.1.

## R3 — Configuración

**Evidencia:** `tech.md` y `structure.md`: "configurar el proveedor/modelo mediante
variables de entorno; nunca hardcodear claves"; la UI de gestión de claves se pospone a
SPEC 6.

Criterios de aceptación:
- 3.1 El proveedor activo y el modelo concreto son seleccionables por configuración (sin
  tocar código).
- 3.2 Los parámetros del modelo (al menos temperatura) son configurables.
- 3.3 Las claves de API se leen exclusivamente de variables de entorno; ninguna clave se
  hardcodea ni se versiona.
- 3.4 Cambiar de proveedor (p.ej. de Ollama a Claude) es un cambio de configuración
  exclusivamente — cero cambios de código en los consumidores.

## R4 — Errores y reintentos

**Evidencia:** patrón ya establecido en `research/sources/base.py::with_retry` (backoff
exponencial ante fallos transitorios de red); el investigador nunca deja que una excepción
cruda de una librería externa aborte la investigación (NFR Reliability de specs previas).

Criterios de aceptación:
- 4.1 Los fallos de red, de clave inválida o de proveedor sin respuesta producen un tipo de
  error **propio** del módulo LLM, nunca la excepción cruda de LangChain o del SDK
  subyacente.
- 4.2 Los fallos transitorios (red, rate-limit) se reintentan con backoff, coherente con el
  patrón ya usado en `research/sources/base.py`.
- 4.3 Los fallos no transitorios (p.ej. clave inválida) no se reintentan indefinidamente:
  fallan con un error propio claro tras el intento.

## R5 — Contador de tokens

**Evidencia:** base necesaria para el futuro control de costes (backlog v1.1); sin
lógica de presupuesto en esta spec.

Criterios de aceptación:
- 5.1 Cada llamada al puerto expone el número de tokens de entrada y de salida
  consumidos por esa llamada concreta.
- 5.2 El contador no implementa límites, presupuestos ni cortes automáticos — eso queda
  para la futura spec de control de costes (backlog v1.1).

## R6 — Filtro semántico de resultados (Opción 1)

**Evidencia:** re-validación T19/R21 del 28-06-2026 (`Contexto_para_mi/checkpoint_2026-06-28.md`):
de 40 resultados de la búsqueda exhaustiva, solo ~7-8 eran convocatorias reales de
cooperación internacional; ~10 eran falsos positivos por coincidir solo con un nombre
propio/lugar ("El Salvador" como parroquia, club o municipio en España, no el país); ~22
eran falsos positivos por tratarse de subvenciones de ámbito nacional/doméstico ajenas a
cooperación internacional ("soberanía alimentaria" en contexto agrícola de Canarias). A
esto se suman los falsos positivos ya descritos en el diagnóstico del 12-06-2026
(`investigador-v2` R15/R16): noticias, estudios/informes, páginas de ONGs, licitaciones y
proyectos ya financiados o resueltos. Nota de la spec: "los falsos positivos B y C son
exactamente el problema que resolverá el filtro semántico LLM de SPEC 2".

Criterios de aceptación:
- 6.1 Por cada resultado de una investigación, el sistema pregunta al LLM si es una
  convocatoria de subvención **ABIERTA** a la que una ONG puede presentarse (SI/NO).
- 6.2 El filtro se aplica a **todos** los resultados de la investigación (Opción 1): no hay
  enrutado previo por `result_type` ni exención de ningún resultado.
- 6.3 El código traduce la respuesta del LLM a un booleano fiable (SI → apto, NO → no
  apto).
- 6.4 Cuando la respuesta del modelo no es interpretable de forma fiable como SI o NO, el
  código la marca como una tercera salida explícita "no clasificado" — nunca se fuerza a
  SI o NO por defecto.
- 6.5 El filtro no modifica ni sustituye `result_type` (`R20` de `investigador-v2`): es una
  clasificación adicional, independiente y por encima de la heurística existente.

---

## Decisiones tomadas (01-07-2026, Kike)

- **Opción 1 confirmada:** el LLM clasifica todos los resultados con una pregunta binaria;
  sin enrutado heurístico ni extracción estructurada en esta spec.
- **Firma del puerto:** system prompt y user prompt separados (ver R1.1) — se detalla la
  razón (alineación con el futuro chat de SPEC 3) en `design.md`.
- **Adaptador genérico OpenAI-compatible:** aplazado a BACKLOG v1.1 (R2.4).
- **Numeración de requisitos:** independiente por spec, ver "Nota de numeración" arriba.
