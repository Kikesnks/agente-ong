"""Contenedor de la alineación estratégica extraída de una convocatoria (R1).

`AlineacionEstrategica` es independiente de `GrantOpportunity`/`research/models.py`
(no se modifican): lo produce el parser (`alignment_parser.py`, R5) a partir de la
respuesta del LLM extractor, y lo consumen el extractor (R7) y la integración en el
pipeline de enrichment (R7), fuera de esta spec en su parte de conexión concreta.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AlineacionEstrategica:
    """Alineación de una convocatoria con el Plan Director 2024-2027.

    Lista vacía en cualquier campo significa "no alineado" o "no procesado",
    indistinguibles a nivel de modelo (decisión aceptada en R1).
    """

    ods: list[int] = field(default_factory=list)
    prioridades_geograficas: list[str] = field(default_factory=list)
    enfoques_transversales: list[str] = field(default_factory=list)
    sectores_plan_director: list[str] = field(default_factory=list)
