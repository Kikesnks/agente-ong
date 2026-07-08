"""Diagnóstico AISLADO de Tavily (fuera del pipeline del investigador).

Investiga por qué Tavily no generó ni un solo hit en los 5 runs reales registrados en
`.data/agente_ong.db` (10-06 a 08-07-2026) pese a no haber ninguna excepción registrada en
`failed_sources` (ver diagnóstico de código previo). Llama directamente a
`TavilyClient.search(..., include_usage=True)` para ver la respuesta cruda de la API,
incluido el campo de uso/créditos que `TavilySource` (`research/sources/tavily.py`) no pide.

NO usa `Investigador` ni `ResearchGraph`: no toca el ledger, no persiste nada en
`.data/agente_ong.db` ni en ningún store. Es una llamada de red aislada, de solo lectura.

Autorización: 1-2 llamadas reales a la API de Tavily (confirmado por el usuario, 09-07-2026).

Uso: python scripts/diagnostico_tavily.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Permite ejecutar el script directamente (python scripts/...) sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import os  # noqa: E402

from tavily import TavilyClient  # noqa: E402

# Mismo formato que usa `ResearchConfig.from_env()` (research/config.py:149): lee
# TAVILY_API_KEY directamente de `os.environ` tras `load_dotenv()`.
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

QUERY_A = "El Salvador soberanía alimentaria cooperación internacional hispanoamérica"
QUERY_B = "convocatoria ODS 2 Hambre cero"


def _print_query_result(label: str, query: str, raw: dict) -> None:
    results = raw.get("results", [])
    print(f"\n=== {label}: {query!r} ===")
    print(f"Resultados devueltos: {len(results)}")

    print("\nPrimeros 3 resultados:")
    if not results:
        print("  (ninguno)")
    for hit in results[:3]:
        print(f"  - title: {hit.get('title')!r}")
        print(f"    url:   {hit.get('url')!r}")
        print(f"    score: {hit.get('score')!r}")

    print("\nCampo 'usage' completo:")
    print(f"  {json.dumps(raw.get('usage'), ensure_ascii=False, indent=2)}")

    otros = {k: v for k, v in raw.items() if k not in ("results", "usage")}
    print("\nOtros campos/metadatos de la respuesta:")
    if otros:
        print(f"  {json.dumps(otros, ensure_ascii=False, indent=2, default=str)}")
    else:
        print("  (ninguno)")


def main() -> int:
    if not TAVILY_API_KEY:
        print("TAVILY_API_KEY no está definida (revisa el .env). Abortando sin llamar a la API.")
        return 1

    client = TavilyClient(api_key=TAVILY_API_KEY)

    for label, query in (("Query A (términos originales)", QUERY_A), ("Query B (formato R25 ODS)", QUERY_B)):
        try:
            raw = client.search(
                query,
                search_depth="advanced",
                max_results=10,
                include_usage=True,
            )
        except Exception as exc:  # noqa: BLE001 - diagnóstico manual: queremos ver CUALQUIER excepción tal cual
            print(f"\n=== {label}: {query!r} ===")
            print(f"EXCEPCIÓN: {type(exc).__name__}: {exc}")
            continue
        _print_query_result(label, query, raw)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
