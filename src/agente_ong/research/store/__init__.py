"""Adaptadores de persistencia del agente investigador.

Expone el puerto `ResearchStore`. Los adaptadores concretos (`InMemoryStore`, `EngramStore`)
se añaden en tareas posteriores y se exportarán aquí cuando existan.
"""

from agente_ong.research.store.base import ResearchStore

__all__ = ["ResearchStore"]
