# Roadmap de specs — agente-ong

*Última actualización: 10-07-2026*

> **Última revisión:** cierre de SPEC 2 / `integracion-llm` con reapertura R7 (T13, commit `e562864`, 09-07-2026). T4/T5 aplazadas por dependencia externa (claves API). Se recogen también las extensiones de `investigador-v2` con R24/R25 (ODS) y UI-36, ejecutadas entre el 22-06 y hoy. Este archivo pasa a documento vivo del sistema, ubicado en la raíz del repo. Fuente autoritativa del estado: `git log` + checkboxes en los `tasks.md` de cada spec.

---

## Estado de completadas

| Módulo | Tareas | Tests | Cierre |
|---|---|---|---|
| investigador v1 | 36/36 | incluidos en total | OK |
| streamlit UI | 33/33 (incluye UI-33) | incluidos en total | OK |
| investigador-v2 (R14–R25) | T1–T18 + T22, T26–T29 en código (R24 y R25 ODS cerradas post-v4); T19/R21 manual pendiente | incluidos en total | OK en código |
| UI-34 (numeración convocatorias) | T34 | +4 tests | OK — commit `42406d1` |
| UI-35 (URL + fecha consultada) | T35 | +4 tests | OK — commit `dd755be` |
| UI-36 (acento verde + título "Datos por confirmar") | T36 | — | OK — commit `0ecad05` |
| integracion-llm (SPEC 2) | 11/13 (T4/T5 aplazadas por claves API) | incluidos en total | OK — R7 cerrada con T13, commit `e562864` |

**Suite total: 340 passed** (`pytest -q`, confirmado 10-07-2026). +74 tests desde el cierre v4 (22-06).

---

## Pendientes inmediatos (no son specs, no tienen orden impuesto entre sí)

1. **investigador-v2 / T19 (R21) — re-validación manual conjunta.** Re-ejecutar las dos búsquedas del diagnóstico del 12-06, documentar antes/después con números absolutos (total resultados, cuántos con importe/plazo, cuántos `convocatoria_probable`) en `Contexto_para_mi/revalidacion_investigador_v2.md`. Material de portafolio. Sin empezar — sin commit.
2. **integracion-llm / T4 — Adaptadores Claude y OpenAI** en `llm/adapters/claude.py` y `openai.py`. Aplazada por dependencia externa (claves API).
3. **integracion-llm / T5 — LLMConfig + build_provider** en `llm/config.py`. Aplazada por dependencia externa (claves API).
   Código relacionado: `src/agente_ong/ui/jobs.py:44` (comentario `# TODO(T5)` en `_OLLAMA_MODEL`).

---

## Orden de ejecución de specs

```
(pendientes inmediatos de arriba, sin orden entre sí)
→ SPEC 3 (chat de proyecto)
→ SPEC 4 (agente redactor)
→ SPEC 5 (orquestación)
→ SPEC 6 (empaquetado)
```

Las specs completas (requirements, design, tasks) se escriben justo antes de ejecutarlas.

---

## SPEC 3: Chat de proyecto

- **Objetivo:** conversación con el LLM sobre los resultados de la investigación y los documentos del proyecto.
- **Ejemplos de uso:** "hazme un resumen del resultado 3, dime plazos y requisitos", "¿cuál es la mejor convocatoria para este proyecto?".
- **Alcance:**
  - Chat en la vista de proyecto con el informe como contexto (numeración UI-34 permite referirse a "resultado N").
  - Documentos de `RECURSOS/[proyecto]/` como contexto adicional — RAG simple por inyección de texto en el prompt; vector store solo si el volumen lo exige (decisión al especificar).
  - Principio rector también en el chat: respuestas trazables al informe/documentos, nunca inventar datos.
- **Decisiones a tomar al especificar:** ¿historial de chat persistido en el `.db` o efímero por sesión? ¿extracción de texto de PDF/DOCX (qué librería)? ¿límite de contexto con muchos documentos (aquí se decide si hace falta vector store)?
- **Dependencias:** SPEC 2 (cerrada) + UI-34 (cerrada).
- **Nota:** el mecanismo documentos → prompt se diseña para que SPEC 4 lo reutilice.

---

## SPEC 4: Agente redactor

- **Objetivo:** generar borradores de propuesta a partir de la convocatoria seleccionada + contexto del proyecto.
- **Alcance:** extracción de requisitos de la convocatoria, generación por secciones, tono ONG auténtico, salida Markdown. Reutiliza el mecanismo de contexto de SPEC 3.
- **Decisión preliminar:** prompts en archivos `.md` cargados por código (patrón skill) — editables sin tocar código, versionados en Git, compatibles con cualquier proveedor LLM.
- **Decisiones a tomar:** ¿grafo LangGraph propio o agente simple? ¿revisión humana por sección o documento completo?
- **Dependencias:** SPEC 2 (cerrada) y SPEC 3.
- **Riesgo principal:** "pasar detectores de IA" es objetivo difuso y cambiante. Al especificar, definir qué significa en concreto y qué es medible.

---

## SPEC 5: Orquestación investigador ↔ redactor en UI

- **Objetivo:** flujo completo — investigar → explorar resultados (chat) → seleccionar convocatoria → redactar → revisar → descargar.
- **Decisiones a tomar:** casi todas dependen del diseño del redactor.
- **Dependencias:** SPEC 4 y la UI.
- **Nota:** puede quedar absorbida en SPEC 4 una vez integrado el chat de SPEC 3. Se decide al terminar SPEC 4.

---

## SPEC 6: Empaquetado e instalación

- **Objetivo:** que una ONG sin perfil técnico instale y use la app.
- **Alcance:** instalación simplificada, gestión de claves API desde la UI, arranque con un clic, datos en ubicación estándar del sistema, guía de usuario.
- **Decisiones a tomar:** ¿instalador real (PyInstaller/Briefcase) o script + acceso directo? ¿Ollama incluido u opcional? La fricción de Streamlit como app local (abre navegador, proceso en terminal): ¿se acepta o se evalúa alternativa?
- **Dependencias:** todas las anteriores. Independiente en diseño: se puede especificar en paralelo.
- **Riesgo principal:** Python 3.14 + dependencias pesadas hacen el empaquetado no trivial. **PoC temprana recomendada** — no descubrir bloqueos al final.

---

## Backlog v1.1 (no bloquean v1)

- Exportación PDF/DOCX de informes y propuestas.
- Vector store sobre `RECURSOS/` (si el RAG simple de SPEC 3 se queda corto).
- Control de costes/tokens (presupuesto por investigación, modo económico vs exhaustivo). Al implementarlo, revisar valores de `DEPTH_PRESETS`.
- Re-comprobación de links bajo demanda.
- Modo autónomo nocturno con informe de sesión.
- Bucle inteligente `verify→search` en el grafo del investigador.
- Generación automática de `query_terms` desde lenguaje natural.
- Refinado de `search_context` con LLM a partir de la descripción del proyecto.

> **Ya fuera de backlog — implementado en investigador-v2:** enriquecimiento BDNS con importe (`presupuestoTotal`) y plazo promovido a R19, implementado en T13. Filtro `min_year` aplicado antes de las llamadas al detalle (R19.2). Vocabulario ODS integrado en `_derive_queries` (R24) y multiselección obligatoria de ODS propagada end-to-end (R25).

---

## Régimen de mantenimiento

Actualizar este archivo al cerrar cada SPEC o reapertura significativa. Frecuencia mínima. Motivo empírico: entre el v4 (22-06-2026) y esta revisión (10-07-2026) el roadmap no se tocó durante 18 días pese a cierres relevantes (`integracion-llm` T1-T13, `investigador-v2` R24/R25, UI-36). Con esta regla no vuelve a pasar.
