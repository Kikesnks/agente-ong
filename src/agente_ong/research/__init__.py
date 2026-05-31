"""Agente investigador — módulo portable de investigación.

Busca convocatorias de subvención (públicas y privadas) y proyectos aprobados de ejemplo,
priorizando calidad y veracidad sobre velocidad: cruza información entre fuentes, nunca
inventa datos, lleva registro persistente de fuentes consultadas e investiga en profundidad.

Diseñado como módulo independiente y portable (ver `.claude/specs/investigador/design.md`).
La superficie pública (`Investigador`, `ResearchConfig`, `ResearchRequest`, `ResearchReport`)
se declarará aquí cuando se implementen sus componentes (tarea 29).
"""

# La API pública se exportará en la tarea 29, una vez implementada la fachada Investigador.
__all__: list[str] = []
