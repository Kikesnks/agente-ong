"""Detección de disponibilidad de un proveedor LLM local (R7, T9).

Ping ligero, sin efectos secundarios: no arranca ningún modelo ni consume
tokens. Usado por la UI (aviso en sidebar) y por el cableado de `jobs.py`
para decidir si construir un proveedor real antes de clasificar.
"""

from __future__ import annotations

import httpx

from agente_ong.llm.adapters.ollama import DEFAULT_BASE_URL


def is_ollama_available(
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 1.0,
) -> bool:
    """Devuelve True si el servidor Ollama responde en base_url.

    Nunca lanza excepción: cualquier fallo de red, timeout o status HTTP
    de error se traduce a False. Ping ligero contra /api/tags (endpoint
    documentado de la API de Ollama que lista modelos disponibles; no
    arranca ningún modelo).
    """
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=timeout)
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False
