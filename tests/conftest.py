"""Configuración compartida de pytest.

Inserta `src/` en `sys.path` para que los tests importen el paquete `agente_ong` sin
necesidad de instalar el proyecto (layout `src/`).
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
