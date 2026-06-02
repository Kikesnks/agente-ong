"""Fuentes de búsqueda/lectura del agente investigador.

Expone la interfaz `SearchSource`, el tipo `Capability` y el helper `with_retry`. Las
fuentes concretas (Tavily, Firecrawl, BDNS, TED) se añaden en tareas posteriores y se
exportarán aquí cuando existan.
"""

from agente_ong.research.sources.base import Capability, SearchSource, with_retry

__all__ = ["SearchSource", "Capability", "with_retry"]
