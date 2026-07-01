"""Puerto de LLM (`LLMProvider`) multi-proveedor.

`LLMProvider` es la interfaz (patrón Ports & Adapters, igual que `SearchSource` en
`research/sources/base.py`) que abstrae qué proveedor concreto responde a una llamada
(Claude, OpenAI, Ollama...). El resto del sistema (filtro semántico, y en el futuro
chat/redactor) depende solo de esta interfaz, nunca de un SDK de proveedor.

Firma B (decisión de SPEC 2, ver design.md R1): `complete` recibe el system prompt y el
user prompt por separado en vez de un único prompt concatenado por el llamador — separa
instrucciones de datos (más robusto frente a contenido no confiable en el user prompt) y
alinea con el futuro chat de SPEC 3 (roles system/user/assistant).

Este módulo es deliberadamente puro-stdlib: ningún adaptador concreto (que sí usa
LangChain) se importa aquí.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Respuesta de una llamada al LLM: texto generado y tokens consumidos."""

    text: str
    input_tokens: int
    output_tokens: int


class LLMProvider(ABC):
    """Proveedor de LLM intercambiable: cualquier implementación satisface este contrato."""

    @abstractmethod
    def complete(self, system: str, user: str) -> LLMResponse:
        """Genera una respuesta a partir de un system prompt y un user prompt separados."""
        raise NotImplementedError
