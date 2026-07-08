"""Mini-experimento AISLADO: 3 variantes de construcción de query contra Tavily.

Sigue al diagnóstico de `scripts/diagnostico_tavily.py` (que confirmó que la API responde
bien con queries "limpias") y al diagnóstico de código de `sources/tavily.py::search()`
(que concatena `search_context` + `query.text` + `call_vocabulary`). Este script prueba,
con llamadas reales, si esa concatenación es la causante de los 0 hits de Tavily en
producción (5 runs reales, 10-06 a 08-07-2026), aislando cada ingrediente:

  - Variante 1 (opción C): solo `query.text` (lo que probó ya `diagnostico_tavily.py`).
  - Variante 2 (opción B): `query.text` + `call_vocabulary`, SIN `search_context`.
  - Variante 3 (opción A): `search_context` + `query.text`, SIN `call_vocabulary`.

Caso real usado: run de la investigación del 05-07-2026 (project 3, `.data/agente_ong.db`,
run id 5): `query_terms`, `search_context` y `call_vocabulary` (default de `config.py`)
tal cual los usó el pipeline.

NO usa `Investigador`, `ResearchGraph` ni `TavilySource`: no toca `tavily.py`, no persiste
nada. Es una llamada de red aislada, de solo lectura, contra `TavilyClient` directamente.

Autorización: 3 llamadas reales (6 créditos, `search_depth="advanced"` = 2 créditos/llamada,
confirmado por el usuario, 09-07-2026).

Uso: python scripts/experimento_tavily_variantes.py
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

# Mismo formato que usa `ResearchConfig.from_env()` (research/config.py:149).
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# --- Caso real (run del 05-07-2026, project 3) ---
QUERY_TERMS = ["el salvador", "soberanía alimentaria", "cooperación internacional", "hispanoamérica"]
SEARCH_CONTEXT = "cooperacion internacional para el desarrollo de zonas rurales deprimidas en El Salvador"
CALL_VOCABULARY = ("convocatoria", "subvención", "ayudas", "bases reguladoras", "plazo de presentación")

# query.text combinada, exactamente como la arma _derive_queries() (graph.py:141):
# `" ".join(terms)`.
QUERY_TEXT = " ".join(QUERY_TERMS)
VOCABULARY_TEXT = " ".join(CALL_VOCABULARY)

VARIANTES = [
    ("Variante 1 (opción C — solo query.text)", QUERY_TEXT),
    ("Variante 2 (opción B — sin search_context)", f"{QUERY_TEXT} {VOCABULARY_TEXT}"),
    ("Variante 3 (opción A — sin call_vocabulary)", f"{SEARCH_CONTEXT} {QUERY_TEXT}"),
]

# Mismos parámetros que TavilySource.search() manda en producción (tavily.py:72-76),
# más include_usage=True para ver el consumo de créditos (que producción no pide).
SEARCH_KWARGS = dict(search_depth="advanced", max_results=10, include_usage=True)


def _run_variant(label: str, texto: str) -> dict:
    print(f"\n=== {label} ===")
    print(f"Texto exacto enviado: {texto!r}")

    client = TavilyClient(api_key=TAVILY_API_KEY)
    try:
        raw = client.search(texto, **SEARCH_KWARGS)
    except Exception as exc:  # noqa: BLE001 - experimento manual: queremos ver CUALQUIER excepción tal cual
        print(f"EXCEPCIÓN: {type(exc).__name__}: {exc}")
        return {"label": label, "texto": texto, "error": str(exc), "results": [], "credits": None}

    results = raw.get("results", [])
    usage = raw.get("usage") or {}
    print(f"Resultados devueltos: {len(results)}")
    print("Primeros 5 resultados:")
    if not results:
        print("  (ninguno)")
    for hit in results[:5]:
        print(f"  - title: {hit.get('title')!r}")
        print(f"    url:   {hit.get('url')!r}")
        print(f"    score: {hit.get('score')!r}")
    print(f"usage: {json.dumps(usage, ensure_ascii=False)}")

    return {
        "label": label,
        "texto": texto,
        "results": results,
        "credits": usage.get("credits"),
    }


def main() -> int:
    if not TAVILY_API_KEY:
        print("TAVILY_API_KEY no está definida (revisa el .env). Abortando sin llamar a la API.")
        return 1

    resumen = [_run_variant(label, texto) for label, texto in VARIANTES]

    print("\n=== Resumen comparativo ===")
    for r in resumen:
        n = len(r["results"])
        top_score = max((h.get("score") or 0 for h in r["results"]), default=None)
        top_score_str = f"{top_score:.4f}" if top_score is not None else "N/A"
        estado = f"{n} resultados — top score {top_score_str} — {r['credits']} créditos"
        if "error" in r:
            estado = f"EXCEPCIÓN: {r['error']}"
        print(f"{r['label']} — {estado}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
