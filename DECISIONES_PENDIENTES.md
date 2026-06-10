# Decisiones pendientes

Decisiones detectadas durante la ejecución autónoma de specs que requieren confirmación del
humano. Cada entrada lleva contexto, opciones y recomendación. Cuando se decida, aplicar el
cambio y mover la entrada a "Resueltas" (al final).

## Abiertas

(ninguna)

## Resueltas

### 2. Mecanismo de inyección de fuentes fake en el smoke E2E (UI-32, AppTest)

**RESUELTA el 2026-06-10 por Kike: opción (b) — monkeypatch en proceso desde el test.**
`Investigador._default_sources` se sustituye por las fakes existentes
(tests/research/fakes.py) + limpieza del singleton del JobManager (`cache_resource`), sin
tocar código de producción. Si futuras versiones de Streamlit rompen este mecanismo,
escalar a la opción (c). Implementada en `tests/ui/test_app_smoke.py`.

**Contexto:** la tarea UI-32 (smoke E2E con `streamlit.testing.v1.AppTest`) debe lanzar una
investigación SIN usar las APIs reales (no gastar cuota de Tavily/Firecrawl ni golpear
BDNS/TED). `app.py` construye el `JobManager` con la factoría real de `Investigador`, que a
su vez construye las fuentes reales en `_default_sources`. Hace falta un punto de inyección
para que el E2E use `FakeSearchSource`/`FakeFetchSource` (tests/research/fakes.py).

**Opciones:**

- **(a) Hook por variable de entorno en `app.py`** (p.ej. `AGENTE_ONG_FAKE_SOURCES=1` hace
  que `_job_manager` use una factoría con fakes).
  - - Introduce código de test en la app de producción; las fakes viven en `tests/` y la app
    no debería importarlas (ni siquiera condicionalmente).

- **(b) Monkeypatch en proceso desde el test (sin tocar la app).** `AppTest` ejecuta el
  script EN EL MISMO proceso que pytest, así que el test puede, antes de `at.run()`:
  `monkeypatch.setattr(Investigador, "_default_sources", staticmethod(lambda cfg: fakes))`
  y limpiar el singleton (`app._job_manager.clear()`). E2E real: app + JobManager +
  Investigador reales, solo las fuentes son fake.
  - - Depende de dos detalles de implementación (que AppTest corre en proceso y de
    `st.cache_resource.clear()`); si Streamlit cambiara eso, el test se rompe.

- **(c) Punto de inyección explícito en `app.py`** (p.ej. `_job_manager` lee una factoría
  de un global del módulo o `st.session_state`, que el test sustituye).
  - - Interfaz pública nueva en la app solo para tests; más visible pero más honesto que (a).

**Recomendación:** **(b)** — no toca código de producción, reutiliza las fakes existentes y
es el patrón pytest estándar (monkeypatch + clear del cache_resource). Si resultara frágil
con versiones futuras de Streamlit, escalar a (c). Evitaría (a): mezcla test y producto.

### 1. Valores concretos de los presets de profundidad (UI-17, R8)

**RESUELTA el 2026-06-10 por Kike: opción (a) — mantener los valores provisionales.**
Se revisará cuando se implemente el control de costes (presupuesto por investigación,
modos económico/exhaustivo). Sin cambios de código: los valores implementados quedan como
definitivos.

**Contexto:** R8 define tres niveles ("rápida" / "normal" / "exhaustiva") con valores
crecientes de `(max_depth, max_pages)` y "normal" por defecto, pero NI requirements.md NI
design.md fijan los números. La tarea UI-17 los deja como `(..)`. Los números afectan al
coste por investigación (consultas a Tavily/Firecrawl) y al tiempo de espera del usuario.

**Valores acordados** en `src/agente_ong/ui/request_builder.py::DEPTH_PRESETS`:

| Nivel | max_depth | max_pages | Racional |
|---|---|---|---|
| rápida | 1 | 10 | Solo los hits de búsqueda, sin seguir enlaces |
| normal | 3 | 50 | Exactamente los defaults actuales del módulo (`DEFAULT_MAX_DEPTH`/`DEFAULT_MAX_PAGES`) |
| exhaustiva | 5 | 150 | Más profundidad y triple de páginas; acotado por `max_queries` (30) |
