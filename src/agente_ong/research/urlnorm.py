"""Normalización de URLs para deduplicación en el registro de fuentes.

`normalize_url` produce una forma canónica estable de una URL para usarla como clave en el
`SourceLedger`: así, dos URLs equivalentes (que solo difieren en mayúsculas del host, orden
de parámetros, fragmento, puerto por defecto o barra final) comparten clave y no se procesan
dos veces (ver requisitos de no-repetición y de evitar ciclos de la spec).
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Puertos por defecto que se eliminan del host para canonicalizar.
_DEFAULT_PORTS = {"http": "80", "https": "443"}


def normalize_url(url: str) -> str:
    """Devuelve la forma canónica de `url` para usarla como clave de deduplicación.

    Normalizaciones aplicadas:
      - `scheme` y host en minúsculas.
      - Se elimina el puerto por defecto del esquema (http:80, https:443).
      - Parámetros de query ordenados de forma estable (conserva claves repetidas y vacías).
      - Se descarta el fragmento (`#...`).
      - Se elimina la barra final del path (salvo que el path sea la raíz `/`).

    No altera la semántica: no toca `www`, ni mayúsculas del path o de los valores de query
    (que sí pueden ser sensibles a mayúsculas). Si la entrada no es parseable, se devuelve
    su versión recortada sin fallar.
    """
    if url is None:
        return ""

    raw = url.strip()
    if not raw:
        return ""

    parts = urlsplit(raw)

    scheme = parts.scheme.lower()

    # Host (netloc) en minúsculas; el host es insensible a mayúsculas. Separamos un posible
    # userinfo (user:pass@) para no tocarlo, aunque es poco habitual.
    netloc = parts.netloc
    userinfo, sep, hostport = netloc.rpartition("@")
    hostport_lower = hostport.lower()

    # Quitar puerto por defecto.
    if ":" in hostport_lower:
        host, _, port = hostport_lower.rpartition(":")
        if port == _DEFAULT_PORTS.get(scheme):
            hostport_lower = host
    netloc = f"{userinfo}{sep}{hostport_lower}" if sep else hostport_lower

    # Path: quitar barra final salvo en la raíz.
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Query: orden estable, conservando claves repetidas y valores vacíos.
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted(query_pairs))

    # Fragmento descartado (se pasa cadena vacía).
    return urlunsplit((scheme, netloc, path, query, ""))
