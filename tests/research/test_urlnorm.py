"""Tests de `normalize_url` (deduplicación de fuentes).

Cubre las normalizaciones que garantizan que dos URLs equivalentes compartan clave en el
`SourceLedger`: mayúsculas del host/esquema, fragmentos, reordenado de query params y barra
final. _Requirements: 5.2_
"""

import pytest

from agente_ong.research.urlnorm import normalize_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        # host y esquema en minúsculas (el path conserva su caja)
        ("HTTPS://BDNS.es/Convocatoria", "https://bdns.es/Convocatoria"),
        ("HtTp://Host.COM/a", "http://host.com/a"),
        # fragmento descartado
        ("https://x.es/a#seccion", "https://x.es/a"),
        ("https://x.es/a?q=1#frag", "https://x.es/a?q=1"),
        # reordenado estable de query params
        ("https://x.es/a?b=2&a=1", "https://x.es/a?a=1&b=2"),
        # barra final eliminada salvo en la raíz
        ("https://x.es/a/", "https://x.es/a"),
        ("https://x.es/", "https://x.es/"),
        # puerto por defecto eliminado; no-default conservado
        ("http://x.es:80/a", "http://x.es/a"),
        ("https://x.es:443/a", "https://x.es/a"),
        ("https://x.es:8443/a", "https://x.es:8443/a"),
        # claves repetidas y valores vacíos conservados, pero ordenados
        ("https://x.es/a?b=&a=1&a=2", "https://x.es/a?a=1&a=2&b="),
        # valores de query sensibles a mayúsculas: NO se tocan
        ("https://x.es/Ruta?q=Hola", "https://x.es/Ruta?q=Hola"),
    ],
)
def test_normalize_url_cases(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_normalize_url_is_idempotent() -> None:
    url = "HTTP://Host.COM:80/p/?z=1&a=2#frag"
    once = normalize_url(url)
    assert normalize_url(once) == once


def test_equivalent_urls_share_key() -> None:
    a = "HTTP://Host.COM:80/p/?z=1&a=2#frag"
    b = "http://host.com/p?a=2&z=1"
    assert normalize_url(a) == normalize_url(b)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_normalize_url_blank_inputs(blank) -> None:
    assert normalize_url(blank) == ""
