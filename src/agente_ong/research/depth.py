"""Control de profundidad y coste de la investigación (`DepthLimiter`).

El principio de producto es "calidad sobre velocidad", pero acotado: una investigación no
puede profundizar ni consultar indefinidamente (evita bucles y costes descontrolados, ver
Requirement 6.3 y NFR Performance). `DepthLimiter` decide si el agente puede seguir
expandiendo en función de la profundidad alcanzada, las páginas leídas y las consultas
lanzadas, contra los límites de `ResearchConfig`.
"""

from __future__ import annotations

from agente_ong.research.config import ResearchConfig


class DepthLimiter:
    """Decide si la investigación puede seguir expandiéndose según los límites de config."""

    def __init__(self, config: ResearchConfig | None = None) -> None:
        cfg = config or ResearchConfig()
        self.max_depth = cfg.max_depth
        self.max_pages = cfg.max_pages
        self.max_queries = cfg.max_queries

    def can_expand(
        self,
        current_depth: int,
        pages_fetched: int,
        queries_made: int = 0,
    ) -> bool:
        """True si se puede seguir expandiendo sin superar ningún límite.

        Devuelve False en cuanto se alcanza (o supera) cualquiera de los topes: profundidad,
        páginas leídas o consultas lanzadas. Así el grafo corta la expansión y compila el
        informe con lo hallado hasta ese punto.
        """
        return (
            current_depth < self.max_depth
            and pages_fetched < self.max_pages
            and queries_made < self.max_queries
        )
