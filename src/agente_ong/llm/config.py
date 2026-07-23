"""Configuración multi-proveedor del módulo LLM (T5a/T5b, reapertura 23-07-2026).

`LLMConfig` selecciona el proveedor activo (`ollama` | `deepseek` | `openai` |
`disabled`) por variable de entorno (`LLM_PROVIDER`), sin exponer `base_url` ni modelo
por entorno para los proveedores de pago: esos dos valores son presets internos del
código (`_PAID_PROVIDER_PRESETS`), fuera de alcance como configuración en esta ronda
(ver `requirements.md` R3.5 y `design.md` de `integracion-llm`). Ollama no requiere
clave; `deepseek`/`openai` leen su propia variable dedicada (`DEEPSEEK_API_KEY`/
`OPENAI_API_KEY`).

`build_provider` (T5b) es el único punto del código, fuera de los propios adaptadores,
que conoce los cuatro nombres de proveedor: resuelve `LLMConfig` a un `LLMProvider` real
o a `None` (fallback silencioso completo, R7.3 — `disabled`, sin clave o no disponible
se comportan todos igual para el consumidor). El mensaje del sidebar
(`describe_llm_status`) es T5c, en tarea separada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agente_ong.llm.adapters.ollama import OllamaProvider
from agente_ong.llm.adapters.openai_compatible import OpenAICompatibleProvider
from agente_ong.llm.health import is_ollama_available
from agente_ong.llm.provider import LLMProvider

# Proveedores válidos (R3.1 de requirements.md); Claude queda fuera de este alcance
# (T4b sigue aplazada, sin clave Anthropic). `build_provider` (T5b) es quien valida si
# el valor leído es uno de estos cuatro; aquí solo se lee y se guarda tal cual.
LLMProviderName = Literal["ollama", "deepseek", "openai", "disabled"]

# Preset del modelo local (mismo valor verificado en vivo en T3 de integracion-llm, hoy
# duplicado en ui/jobs.py::_OLLAMA_MODEL — T5d retira ese duplicado al cablear
# build_provider sobre este preset).
_OLLAMA_MODEL_PRESET = "qwen2.5:7b"

# Presets internos de los proveedores de pago: (base_url, model). R3.5 — no
# configurables por variable de entorno en este alcance (evita apuntar por error a un
# endpoint no verificado). NO verificados en vivo todavía (sin DEEPSEEK_API_KEY ni
# OPENAI_API_KEY disponibles en esta sesión): mismo principio de decisiones_pendientes.md
# #11 — confirmar en vivo antes de confiar en estos valores en producción.
_PAID_PROVIDER_PRESETS: dict[str, tuple[str, str]] = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
}


def _env_float(name: str, default: float) -> float:
    """Lee un float de una variable de entorno; usa `default` si falta o es inválida."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class LLMConfig:
    """Configuración inyectable del proveedor LLM activo.

    Las claves de los proveedores de pago son opcionales: sin la clave del proveedor
    seleccionado, `build_provider` (T5b) devolverá `None` — la construcción de
    `LLMConfig` en sí nunca falla por una clave ausente, mismo principio que
    `ResearchConfig` (`research/config.py`).
    """

    provider: LLMProviderName = "ollama"
    provider_explicit: bool = True
    temperature: float = 0.0
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Construye la configuración a partir de variables de entorno.

        Variables reconocidas:
          - LLM_PROVIDER ("ollama" | "deepseek" | "openai" | "disabled"). Si no está
            definida (o está vacía): `provider="ollama"`, `provider_explicit=False` —
            preserva el comportamiento actual del pipeline, que hoy intenta Ollama
            incondicionalmente sin ninguna variable de por medio. Si está definida, a
            cualquier valor (válido o no): `provider_explicit=True`; la validación de
            valores reconocidos es de `build_provider` (T5b), no de este método.
          - LLM_TEMPERATURE (float; default 0.0 si falta o es inválida)
          - DEEPSEEK_API_KEY, OPENAI_API_KEY (Ollama no requiere clave; se leen ambas
            aunque solo se use la del proveedor seleccionado — esa selección es de
            `build_provider`, T5b)

        Antes de leer nada carga `.env` (si existe), mismo patrón que
        `ResearchConfig.from_env()`. Import perezoso: solo hace falta al construir la
        config, no al importar este módulo.
        """
        from dotenv import load_dotenv

        # Sube desde src/agente_ong/llm/config.py hasta la raíz del repo — misma
        # profundidad que research/config.py (llm/ y research/ son paquetes hermanos
        # bajo agente_ong/); si la estructura del paquete cambia, actualizar parents[...].
        env_path = Path(__file__).resolve().parents[3] / ".env"
        # override=False: una variable YA presente en el proceso (exportada a mano, o
        # copiada desde `st.secrets` por la UI antes de llegar aquí) gana siempre sobre
        # el valor del `.env`. Si el archivo no existe, `load_dotenv` no hace nada.
        load_dotenv(env_path, override=False)

        raw_provider = os.environ.get("LLM_PROVIDER")
        if raw_provider is None or raw_provider.strip() == "":
            provider = "ollama"
            provider_explicit = False
        else:
            provider = raw_provider.strip()
            provider_explicit = True

        return cls(
            provider=provider,
            provider_explicit=provider_explicit,
            temperature=_env_float("LLM_TEMPERATURE", 0.0),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
        )


def build_provider(config: LLMConfig) -> LLMProvider | None:
    """Resuelve `config` a un `LLMProvider` real, o a `None` si no hay uno usable.

    Sin excepciones: ninguna rama propaga un fallo crudo al consumidor. Las tres
    situaciones siguientes son indistinguibles desde fuera — todas devuelven `None`
    (fallback silencioso completo, R7.3): `provider == "disabled"`, el proveedor
    seleccionado carece de la clave de API requerida, o el proveedor seleccionado no
    responde (hoy solo aplica a `"ollama"`, vía `is_ollama_available`). Un valor de
    `provider` no reconocido (ni `"ollama"`, ni una clave de `_PAID_PROVIDER_PRESETS`,
    ni `"disabled"`) también devuelve `None`, nunca lanza.

    Único punto del código, fuera de los propios adaptadores, que conoce los cuatro
    nombres de proveedor (ver docstring del módulo).
    """
    if config.provider == "disabled":
        return None

    if config.provider == "ollama":
        if not is_ollama_available():
            return None
        return OllamaProvider(model=_OLLAMA_MODEL_PRESET, temperature=config.temperature)

    if config.provider in _PAID_PROVIDER_PRESETS:
        api_key = (
            config.deepseek_api_key
            if config.provider == "deepseek"
            else config.openai_api_key
        )
        if not api_key:
            return None
        base_url, model = _PAID_PROVIDER_PRESETS[config.provider]
        return OpenAICompatibleProvider(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=config.temperature,
        )

    # Valor de provider no reconocido (ni ollama, ni un preset de pago, ni disabled):
    # nunca excepción, mismo principio de "nunca lanza" que is_ollama_available.
    return None
