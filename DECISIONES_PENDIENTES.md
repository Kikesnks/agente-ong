# Decisiones pendientes

Decisiones detectadas durante la ejecución autónoma de specs que requieren confirmación del
humano. Cada entrada lleva contexto, opciones y recomendación. Cuando se decida, aplicar el
cambio y mover la entrada a "Resueltas" (al final).

## Abiertas

(ninguna)

## Resueltas

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
