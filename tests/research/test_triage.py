"""Tests de la pre-clasificación heurística de resultados (`research/triage.py`, R20)."""

from __future__ import annotations

from agente_ong.research.models import SearchHit
from agente_ong.research.triage import best_result_type, classify_hit


def _hit(**kw) -> SearchHit:
    kw.setdefault("url", "https://example.org/x")
    kw.setdefault("source_name", "tavily")
    return SearchHit(**kw)


# --- classify_hit ---


def test_bdns_hit_is_always_convocatoria_probable() -> None:
    # El corpus de BDNS es solo convocatorias, sin importar el título.
    assert classify_hit(_hit(source_name="bdns", title="lo que sea")) == "convocatoria_probable"


def test_strong_signals_make_convocatoria_probable() -> None:
    hit = _hit(
        title="Convocatoria de ayudas 2026",
        snippet="Bases reguladoras y plazo de presentación hasta septiembre.",
    )
    assert classify_hit(hit) == "convocatoria_probable"


def test_amount_plus_one_signal_is_convocatoria_probable() -> None:
    hit = _hit(title="Subvención para cultura", snippet="Dotación de 50.000 €.")
    assert classify_hit(hit) == "convocatoria_probable"


def test_official_domain_is_convocatoria_probable_even_without_signals() -> None:
    hit = _hit(url="https://sede.gob.es/algo", title="Trámite", snippet="ficha")
    assert classify_hit(hit) == "convocatoria_probable"


def test_tavily_without_strong_signal_is_documento_informativo() -> None:
    # R16.5: Tavily sin señal fuerte queda como material informativo.
    hit = _hit(
        title="Estudio sobre pobreza rural",
        snippet="Análisis de la ejecución de fondos en proyectos ya financiados.",
    )
    assert classify_hit(hit) == "documento_informativo"


def test_non_tavily_non_official_without_signals_is_desconocido() -> None:
    hit = _hit(source_name="otra", url="https://blog.example/post", title="Noticia")
    assert classify_hit(hit) == "desconocido"


# --- best_result_type ---


def test_best_result_type_prefers_convocatoria_then_desconocido() -> None:
    assert best_result_type(["documento_informativo", "convocatoria_probable"]) == (
        "convocatoria_probable"
    )
    assert best_result_type(["documento_informativo", "desconocido"]) == "desconocido"
    assert best_result_type([]) == "desconocido"
