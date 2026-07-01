"""Abstracción multi-proveedor de LLM (SPEC 2).

Puerto `LLMProvider` (patrón Ports & Adapters, igual que `SearchSource` en
`agente_ong.research.sources.base`) que desacopla el resto del sistema del proveedor
concreto de LLM (Claude, OpenAI, Ollama...). Ver `.claude/specs/integracion-llm/design.md`.
"""

from agente_ong.llm.provider import LLMProvider, LLMResponse

__all__ = [
    "LLMProvider",
    "LLMResponse",
]
