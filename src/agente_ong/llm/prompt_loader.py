"""Cargador genérico de prompts en archivo (patrón "skill", R6).

Los prompts viven como archivos `.md` en `llm/prompts/`, editables sin tocar código
Python. `load_prompt` es deliberadamente genérico (no específico del filtro semántico)
para que el agente redactor de SPEC 4 lo reutilice tal cual.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Devuelve el contenido del prompt `<name>.md` en `llm/prompts/`.

    Lanza `FileNotFoundError` con un mensaje claro si el archivo no existe, en vez de
    dejar escapar el error genérico de `pathlib`/`open`.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        msg = f"No existe el prompt '{name}' (esperado en {path})"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")
