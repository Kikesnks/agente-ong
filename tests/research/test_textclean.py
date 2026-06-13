"""Tests de la limpieza de contenido web (`research/textclean.py`, R18).

Casos basados en los elementos de plantilla reales del diagnóstico del 12-06-2026
("Skip to content", "ES / CAT", aviso de cookies) y garantía de que el texto útil NO se
pierde. _Requirements: 18.1, 18.2_
"""

from __future__ import annotations

from agente_ong.research.textclean import clean_text, snippet


# --- clean_text: elementos de plantilla fuera ---


def test_removes_cookie_and_nav_and_language_lines() -> None:
    raw = "\n".join(
        [
            "Skip to content",
            "ES / CAT / EN",
            "Nuestra web utiliza cookies para mejorar la experiencia.",
            "Convocatoria de subvenciones para proyectos de cooperación 2026.",
            "El plazo de presentación finaliza el 30 de septiembre.",
            "Síguenos en redes sociales",
            "Todos los derechos reservados",
        ]
    )
    cleaned = clean_text(raw)
    assert "Skip to content" not in cleaned
    assert "ES / CAT / EN" not in cleaned
    assert "cookies" not in cleaned
    assert "Síguenos" not in cleaned
    assert "derechos reservados" not in cleaned
    # El contenido útil se conserva íntegro.
    assert "Convocatoria de subvenciones para proyectos de cooperación 2026." in cleaned
    assert "El plazo de presentación finaliza el 30 de septiembre." in cleaned


def test_keeps_useful_paragraph_mentioning_cookie_in_passing() -> None:
    # Un párrafo largo y legítimo que menciona "cookie" no se descarta (supera el límite
    # de longitud de línea de plantilla).
    parrafo = (
        "La convocatoria financia proyectos de seguridad alimentaria en zonas rurales, "
        "con un presupuesto total de 500.000 euros y, entre los requisitos técnicos, la "
        "plataforma de solicitud puede requerir aceptar una cookie de sesión para operar."
    )
    assert clean_text(parrafo) == parrafo


def test_collapses_whitespace_and_duplicate_lines() -> None:
    raw = "Convocatoria   abierta\nConvocatoria abierta\n\n  Plazo:   30 días  "
    cleaned = clean_text(raw)
    assert cleaned == "Convocatoria abierta\nPlazo: 30 días"


def test_empty_and_none_return_empty() -> None:
    assert clean_text(None) == ""
    assert clean_text("   \n  \n") == ""


# --- snippet: longitud máxima en límite de palabra ---


def test_snippet_truncates_on_word_boundary_with_ellipsis() -> None:
    text = "convocatoria de subvenciones para cooperación internacional y desarrollo"
    out = snippet(text, 30)
    assert len(out) <= 31  # 30 + elipsis, sin partir palabra
    assert out.endswith("…")
    assert not out[:-1].endswith(" ")
    assert text.startswith(out[:-1].rstrip("…").rstrip())


def test_snippet_keeps_short_text_unchanged() -> None:
    assert snippet("texto corto", 100) == "texto corto"


def test_snippet_collapses_internal_whitespace() -> None:
    assert snippet("a   b\n c", 100) == "a b c"


def test_snippet_empty() -> None:
    assert snippet(None, 50) == "" and snippet("", 50) == ""
