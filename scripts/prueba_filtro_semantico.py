"""Prueba MANUAL de calidad del filtro semántico (SPEC 2) sobre una investigación real.

NO es parte de la suite automatizada ni de ninguna tarea de la spec (T4/T5 siguen
aplazadas, pendientes de claves API): es una comprobación cualitativa del prompt
(`llm/prompts/semantic_filter.md`) contra un caso real con el ruido conocido del
diagnóstico (Tipo B: nombre propio/lugar sin relación; Tipo C: ámbito nacional/doméstico
ajeno a cooperación internacional — ver `Contexto_para_mi/checkpoint_2026-06-28.md`),
usando Ollama + qwen2.5:7b en local (adaptador de T3).

Uso: python scripts/prueba_filtro_semantico.py
Requisitos: Ollama corriendo (http://localhost:11434) con qwen2.5:7b descargado; venv
activo con las dependencias del proyecto instaladas; TAVILY_API_KEY/FIRECRAWL_API_KEY
EXPORTADAS a mano en el mismo shell antes de lanzar el script si se quieren esas fuentes
activas (igual que la app real: ningún código de `src/` carga `.env`, ver README).

Salida: por consola y en `Informes/prueba_filtro_AAAA-MM-DD_HHMM.md` (`Informes/` está en
`.gitignore`, no se sube al repo).
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

# Permite ejecutar el script directamente (python scripts/...) sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agente_ong.llm.adapters.ollama import OllamaProvider  # noqa: E402
from agente_ong.llm.errors import LLMConnectionError, LLMError  # noqa: E402
from agente_ong.llm.filter_report import classify_report  # noqa: E402
from agente_ong.llm.health import is_ollama_available  # noqa: E402
from agente_ong.llm.provider import LLMProvider, LLMResponse  # noqa: E402
from agente_ong.research.config import ResearchConfig  # noqa: E402
from agente_ong.research.investigador import Investigador  # noqa: E402
from agente_ong.research.models import ResearchReport  # noqa: E402
from agente_ong.ui.request_builder import build  # noqa: E402

MODEL = "qwen2.5:7b"

# Mismos términos y contexto del diagnóstico real (12-06/28-06-2026, ver
# Contexto_para_mi/descripcion_proyecto.md y checkpoint_2026-06-28.md): reproduce el ruido
# conocido (Tipo B/Tipo C) contra el que se redactó el prompt del filtro (R6 de
# .claude/specs/integracion-llm/requirements.md).
QUERY_TERMS = ["el salvador", "soberanía alimentaria", "cooperación internacional", "hispanoamérica"]
SEARCH_CONTEXT = "cooperación internacional para el desarrollo de zonas rurales deprimidas en El Salvador"
DEPTH_LEVEL = "exhaustiva"  # mismo nivel que dio 40 resultados en la re-validación del 28-06

REPORT_DIR = Path(__file__).resolve().parent.parent / "Informes"

TRUNC_TITLE = 80
TRUNC_SNIPPET = 200


class _RecordingProvider(LLMProvider):
    """Envoltorio local (no toca `llm/`) que registra cada llamada real al proveedor
    (user prompt enviado, respuesta y tokens) para poder mostrarla en el informe de esta
    prueba manual. `classify_report` solo devuelve la clasificación final por
    oportunidad, no el detalle de cada llamada — este envoltorio lo captura sin modificar
    `filter_report.py`.
    """

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.records: list[dict] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        try:
            response = self._inner.complete(system, user)
        except LLMError as exc:
            self.records.append({"user": user, "error": str(exc), "input_tokens": 0, "output_tokens": 0})
            raise
        self.records.append(
            {
                "user": user,
                "text": response.text,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        return response


def _truncate(text: str, length: int) -> str:
    text = " ".join(text.split())  # colapsa saltos de línea internos para la tabla
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _parse_user_prompt(user: str) -> tuple[str, str]:
    """Recupera título y extracto del user prompt tal como los arma `semantic_filter.py`
    (`f"Título: {title}\\nExtracto: {snippet}"`)."""
    title_line, _, rest = user.partition("\n")
    title = title_line.removeprefix("Título: ")
    snippet = rest.removeprefix("Extracto: ")
    return title, snippet


def _preflight_ollama(provider: OllamaProvider) -> bool:
    """Comprobación rápida: ¿responde Ollama, y responde el modelo concreto de esta prueba?

    Dos niveles (T9, R7): primero `is_ollama_available()` (ping ligero a `/api/tags`, no
    arranca ningún modelo) para descartar temprano un servidor caído sin gastar tiempo en
    una inferencia real; solo si eso pasa, se hace la inferencia real de este script contra
    `MODEL` — sigue teniendo sentido aquí porque esta prueba manual valida ESE modelo
    concreto, no solo que el servidor esté vivo.
    """
    if not is_ollama_available():
        return False
    try:
        provider.complete("Responde solo OK.", "ping")
    except LLMConnectionError:
        return False
    return True


def _run_investigacion() -> ResearchReport:
    base_config = ResearchConfig.from_env()
    # Modo efímero (db_path=None): prueba manual puntual, no debe mezclarse con el
    # ledger real del producto ni con .data/agente_ong.db.
    config = replace(base_config, db_path=None)
    _, request = build(
        config,
        terms=QUERY_TERMS,
        depth_level=DEPTH_LEVEL,
        search_context=SEARCH_CONTEXT,
    )
    with Investigador(config) as investigador:
        return investigador.run(request)


def _build_lines(
    report: ResearchReport,
    classifications: dict[int, str],
    records: list[dict],
    elapsed: float,
    started_at: datetime,
) -> list[str]:
    n = len(report.opportunities)
    counts = {"si": 0, "no": 0, "no_clasificado": 0}
    lines: list[str] = []

    lines.append("# Prueba manual del filtro semántico (SPEC 2)")
    lines.append("")
    lines.append(f"- Fecha/hora: {started_at.strftime('%d-%m-%Y %H:%M:%S')}")
    lines.append(f"- Modelo: {MODEL} (Ollama local)")
    lines.append(f"- Términos: {', '.join(QUERY_TERMS)}")
    lines.append(f"- Contexto de búsqueda: {SEARCH_CONTEXT}")
    lines.append(f"- Nivel de profundidad: {DEPTH_LEVEL}")
    lines.append(f"- Oportunidades encontradas: {n}")
    if report.failed_sources:
        fallidas = ", ".join(sorted({f.source_name for f in report.failed_sources}))
        lines.append(f"- Fuentes con problemas durante la investigación: {fallidas}")
    lines.append("")
    lines.append("## Clasificación por oportunidad")
    lines.append("")

    for i, opp in enumerate(report.opportunities, start=1):
        result = classifications.get(id(opp), "no_clasificado")
        counts[result] = counts.get(result, 0) + 1
        record = records[i - 1] if i - 1 < len(records) else {}
        title = _truncate(opp.title.value or "(sin título)", TRUNC_TITLE)
        _, sent_snippet = _parse_user_prompt(record.get("user", ""))
        snippet = _truncate(sent_snippet, TRUNC_SNIPPET)
        lines.append(f"{i}. [{result.upper()}] {title}")
        lines.append(f"   Extracto enviado: {snippet or '(vacío)'}")
        if "error" in record:
            lines.append(f"   (fallo del proveedor: {record['error']})")
        lines.append("")

    total_input = sum(r.get("input_tokens", 0) for r in records)
    total_output = sum(r.get("output_tokens", 0) for r in records)
    avg = elapsed / n if n else 0.0

    lines.append("## Resumen")
    lines.append("")
    lines.append(f"- SI: {counts['si']}")
    lines.append(f"- NO: {counts['no']}")
    lines.append(f"- no_clasificado: {counts['no_clasificado']}")
    lines.append(f"- Tiempo total de clasificación: {elapsed:.1f} s")
    lines.append(f"- Tiempo medio por oportunidad: {avg:.2f} s")
    lines.append(f"- Tokens de entrada (total): {total_input}")
    lines.append(f"- Tokens de salida (total): {total_output}")

    return lines


def _print_and_save(
    report: ResearchReport,
    classifications: dict[int, str],
    records: list[dict],
    elapsed: float,
    started_at: datetime,
) -> None:
    lines = _build_lines(report, classifications, records, elapsed, started_at)
    print()
    print("\n".join(lines))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / f"prueba_filtro_{started_at.strftime('%Y-%m-%d_%H%M')}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nInforme guardado en: {out_path}")


def _warn_missing_keys() -> None:
    """Avisa (sin abortar) si TAVILY_API_KEY/FIRECRAWL_API_KEY no están exportadas en el
    entorno del proceso — mismo mecanismo que la app real (ningún código de `src/` carga
    `.env`; solo lee variables ya presentes en `os.environ`)."""
    if not os.environ.get("TAVILY_API_KEY"):
        print(
            "Aviso: TAVILY_API_KEY no está exportada; la búsqueda web (Tavily) no estará "
            "activa. Exporta la variable antes de lanzar el script si quieres Tavily activo."
        )
    if not os.environ.get("FIRECRAWL_API_KEY"):
        print(
            "Aviso: FIRECRAWL_API_KEY no está exportada; el fallback de lectura (Firecrawl) "
            "no estará disponible (el lector propio, sin coste, sigue activo igualmente)."
        )


def main() -> int:
    _warn_missing_keys()
    provider = OllamaProvider(model=MODEL)

    print(f"Comprobando que Ollama responde ({MODEL})...")
    if not _preflight_ollama(provider):
        print("Ollama no responde, ¿está arrancado? (esperado en http://localhost:11434)")
        return 1

    print(f"Lanzando investigación real (modo calls, nivel '{DEPTH_LEVEL}')...")
    try:
        report = _run_investigacion()
    except Exception as exc:  # noqa: BLE001 - prueba manual: mensaje claro, sin traceback crudo
        print(f"La investigación falló: {type(exc).__name__}: {exc}")
        return 1

    print(f"Investigación completa: {len(report.opportunities)} oportunidades encontradas.")

    print("Clasificando con el filtro semántico...")
    recording = _RecordingProvider(provider)
    started_at = datetime.now()
    start = time.perf_counter()
    classifications = classify_report(recording, report)
    elapsed = time.perf_counter() - start

    _print_and_save(report, classifications, recording.records, elapsed, started_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
