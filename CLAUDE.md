# CLAUDE.md — Reglas de operación del proyecto agente-ong

Este archivo lo lee Claude Code (VSC) automáticamente al arrancar en este repo.
Define cómo trabajamos. No describe el estado actual del proyecto (para eso están
`estado_proyecto.md` y `decisiones_pendientes.md` en la raíz).

---

## 1. Identidad del proyecto

- **Nombre:** agente-ong
- **Propósito:** aplicación Python/Streamlit que ayuda a ONGs españolas de
  cooperación internacional a (a) encontrar convocatorias de subvención y
  (b) redactar propuestas competitivas.
- **Metodología:** SDD (Spec-Driven Development, de LIDR) + Ports & Adapters.
- **Stack:** Python, Streamlit, LangChain/LangGraph, SQLite, Ollama local
  (qwen2.5:7b) para LLM gratuito, Tavily + BDNS como fuentes de búsqueda.
- **Entry point UI:** `src/agente_ong/ui/app.py`.
  Arranque local: `streamlit run src/agente_ong/ui/app.py`.
- **Despliegue:** Streamlit Cloud, auto-deploy en push a `main`.

---

## 2. Reparto de roles Claude.ai ↔ VSC

- **Claude.ai (Opus):** planificación, arquitectura, decisiones conceptuales,
  redacción de specs, enseñanza. Kike lo usa desde móvil u ordenador.
- **Claude Code en VSC (Sonnet):** ejecución pura. Sin explicaciones didácticas
  salvo cuando la ejecución lo requiera (errores, decisiones técnicas
  inesperadas, confirmaciones necesarias).
- **Móvil ≠ solo diseño.** Móvil = no ejecutar código. Sí puede diseñar spec.

---

## 3. Protocolo de arranque de sesión (VSC)

Al abrir una sesión nueva, en este orden:

1. Recuperar contexto de ENGRAM: `mem_context(project="agente-ong")`.
2. Leer `estado_proyecto.md` y `decisiones_pendientes.md` (raíz).
3. Si hay spec activa, leer los 3 archivos de `.claude/specs/<spec-activa>/`.
4. `git log -5` → confirmar HEAD esperado y sincronización con remoto.
5. `git status` → confirmar working tree.
6. `pytest -q` → confirmar suite en verde.
7. Si algo no cuadra, parar y reportar. No arrancar tarea nueva.

---

## 4. Reglas de ejecución

- **Entorno virtual siempre activo** antes de cualquier comando Python.
- **`git push` lo hace Kike manualmente** desde terminal normal de VSC. Nunca
  Claude Code (el sandbox bloquea red). Nunca en un prompt como paso automático.
- **`.claude/specs/` SÍ se commitea.** No está en `.gitignore`; el historial del
  repo tiene commits `docs(spec):` bajo `.claude/specs/` desde el inicio del
  proyecto. Las specs son la fuente de verdad versionada del trabajo SDD.
- **Fuentes de verdad:**
  - Estado de ejecución: `tasks.md` de la spec activa + git log.
  - Requisitos: `.claude/specs/<spec>/requirements.md` (R-numbers).
  - Contexto operativo: `estado_proyecto.md`, `decisiones_pendientes.md`.

---

## 5. Convenciones de commits

- **Separar código de documentación.**
  - Código: `feat:`, `fix:`, `test:`, `style:`, `refactor:`.
  - Docs: `docs(spec):`, `docs:`.
- **`git add` con rutas específicas.** Nunca `git add .`.
- **Granularidad:**
  - Código, spec, arquitectura, decisiones consecuentes → un commit por tarea.
  - Tareas puramente textuales (docs, notas, checkboxes) → agrupar en un
    commit único.

---

## 6. Reglas de spec (SDD)

- **Patrón obligatorio de `tasks.md`:**
  ```
  # Implementation Plan

  - [ ] N. Nombre de la tarea
    - Files: rutas específicas
    - Purpose: qué hace y por qué
    - _Leverage: pistas de código existente reutilizable_
    - _Requirements: R-numbers de requirements.md_
    - _Done: criterios de cierre_
  ```
- **Antes de redactar cualquier `requirements.md`, `design.md` o `tasks.md`,**
  leer un archivo de referencia del proyecto para replicar patrón exacto.
- **`_Leverage_` es pista, no contrato.** Verificar al ejecutar la tarea; si la
  referencia está desalineada, ajustar y documentar en el commit.
- **Alineación spec↔código:** si el código tomó la decisión correcta y el spec
  contradice, alinear el spec al código (no al revés). Documentar el porqué.
- **Mini-spec threshold:** tareas mecánicas pequeñas no llevan mini-spec; van a
  `decisiones_pendientes.md` y se ejecutan directamente.

---

## 7. Reglas de ejecución de tareas de spec

- **Un prompt por tarea consecuente** (código, spec, arquitectura). Revisión
  explícita antes de continuar.
- **Batch permitido** para tareas triviales de bajo riesgo (commits, checkboxes,
  notas): "continúa si todo va bien; para solo ante error real".
- **`/clear` entre bloques** para evitar deriva de contexto.
- **Sanity checks (`grep`, etc.)** solo sobre archivos que la tarea toca, no
  sobre directorios enteros.
- **Task scope rule:** si una tarea reescribe un modelo público o elimina una
  función pública, todas las referencias textuales (docstrings, comentarios,
  asserts) en cualquier archivo están en scope aunque no se listen.

---

## 8. Reglas de calidad

- **Filtros LLM = problema de prompt, no de código.** La calibración del filtro
  semántico se hace en el `.md` del prompt, nunca tocando el codebase.
- **Show don't hide:** ante rechazos del filtro, mostrar al usuario con motivo
  etiquetado, no ocultar.
- **False diagnosis principle:** un spec puede ser válido aunque su hipótesis
  original fuese incorrecta. No descartar por eso.
- **Deduplicación de decisiones:** antes de crear una decisión numerada nueva
  en `decisiones_pendientes.md`, comprobar que no exista ya.
- **Fuentes primarias** para taxonomías cerradas. No conformarse con derivados.

---

## 9. Comunicación con Kike

- Respuestas cortas, al grano, español llano.
- Sin adulación ("buena pregunta", "excelente idea", etc.). Solo elogiar cuando
  algo brille de verdad.
- Sin jergas innecesarias. Términos técnicos en inglés → dar significado.
- **Dos opciones solo cuando la decisión sea importante**, con una recomendada
  y su porqué. No dar opciones para todo.
- **Nunca inventar.** Si no se sabe algo, decirlo. Fuentes trazables.
- **Decisiones tomadas por Claude por su cuenta** al preparar un prompt →
  listarlas al final del mensaje para revisión de Kike.

---

## 10. Convenciones de archivos y nombres

- **Contextos:** un archivo vivo por tema, actualizado in-place, nunca versionado
  por fecha en el nombre. Los archivos antiguos van a `OLD/`.
- **`Contexto_para_mi/`:** gitignored, para archivos de contexto de sesión.
- **Specs:** `.claude/specs/<nombre-spec>/` con `requirements.md`, `design.md`,
  `tasks.md`.

---

## 11. Herramientas MCP disponibles

- **ENGRAM:** memoria persistente entre sesiones. Usar siempre al arrancar y
  al cerrar sesión con hallazgos relevantes.
