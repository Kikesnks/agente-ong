"""Política de veracidad y verificación cruzada (`VerificationPolicy`).

Encarna el principio de producto "calidad y verificación cruzada por encima de velocidad":
asigna a cada dato (`Claim`) un `VerificationStatus` según cuántas fuentes lo respaldan y si
son oficiales, y señala las contradicciones en lugar de elegir en silencio.

Reglas de clasificación (Requirements 3.3, 3.4, 4.2, 4.4):

  - Fuentes contradictorias presentes        -> CONFLICTING
  - Sin valor / sin fuentes de respaldo       -> NOT_FOUND
  - >= 2 fuentes de respaldo                   -> VERIFIED
  - 1 fuente de respaldo, oficial              -> OFFICIAL_UNCROSSED   (aceptable, no cruzada)
  - 1 fuente de respaldo, no oficial           -> UNCROSSED_UNVERIFIED (preocupante)

La política de revalidación por caducidad (flag `stale`) se añade en la tarea 14.
"""

from __future__ import annotations

from collections.abc import Sequence

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import Claim, SourceRef, VerificationStatus


class VerificationPolicy:
    """Decide el estado de verificación de los datos según sus fuentes de respaldo."""

    def __init__(self, config: ResearchConfig | None = None) -> None:
        # La config se usa en la política de revalidación (staleness_days), tarea 14.
        self._config = config or ResearchConfig()

    def classify(
        self,
        claim: Claim,
        supporting: Sequence[SourceRef],
        conflicting: Sequence[SourceRef] = (),
    ) -> VerificationStatus:
        """Clasifica un `claim` dado el reparto de fuentes en respaldo y contradicción.

        Args:
            claim: el dato a clasificar (su `value is None` => no encontrado).
            supporting: fuentes que respaldan el valor del claim.
            conflicting: fuentes que reportan un valor distinto (contradicción). Si hay
                alguna, se prioriza señalar la discrepancia (`CONFLICTING`).
        """
        # 1) Una contradicción siempre se señala (no se elige una fuente en silencio).
        if conflicting:
            return VerificationStatus.CONFLICTING

        # 2) Sin valor o sin respaldo => no encontrado.
        if claim.value is None or len(supporting) == 0:
            return VerificationStatus.NOT_FOUND

        # 3) Corroborado por dos o más fuentes => verificado.
        if len(supporting) >= 2:
            return VerificationStatus.VERIFIED

        # 4) Una sola fuente: depende de si es oficial.
        only = supporting[0]
        if only.is_official:
            return VerificationStatus.OFFICIAL_UNCROSSED
        return VerificationStatus.UNCROSSED_UNVERIFIED
