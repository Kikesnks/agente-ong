"""Agente investigador — módulo portable de investigación.

Busca convocatorias de subvención (públicas y privadas) y proyectos aprobados de ejemplo,
priorizando calidad y veracidad sobre velocidad: cruza información entre fuentes, nunca
inventa datos, lleva registro persistente de fuentes consultadas e investiga en profundidad.

Diseñado como módulo independiente y portable (ver `.claude/specs/investigador/design.md`).

Uso básico:

    from agente_ong.research import Investigador, ResearchConfig, ResearchRequest

    investigador = Investigador(ResearchConfig.from_env())
    informe = investigador.run(ResearchRequest(mode="calls", query_terms=["cultura"]))
"""

from agente_ong.research.config import ResearchConfig
from agente_ong.research.investigador import Investigador
from agente_ong.research.models import ResearchReport, ResearchRequest

__all__ = [
    "Investigador",
    "ResearchConfig",
    "ResearchRequest",
    "ResearchReport",
]
