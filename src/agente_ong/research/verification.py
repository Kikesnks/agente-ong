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
from datetime import datetime, timedelta, timezone

from agente_ong.research.config import ResearchConfig
from agente_ong.research.models import Claim, Intent, SourceRef, VerificationStatus


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

    def needs_revalidation(
        self,
        claim: Claim,
        *,
        intent: Intent,
        now: datetime | None = None,
        from_ledger_only: bool = False,
    ) -> bool:
        """Indica si un dato debe revalidarse contra su fuente antes de darlo por bueno.

        El `content_summary` persistido del ledger es solo una PISTA, nunca un dato
        definitivo: por eso los datos críticos que se vayan a usar en una propuesta, los
        caducados, o los que solo provengan de una pista no reconfirmada, exigen reconsulta.

        Devuelve True si se cumple alguna condición (Requirements 3.4, 4.1, 4.3):
          - el dato es crítico y el `intent` es "use_in_proposal";
          - el dato está caducado (su fuente más reciente supera `staleness_days`);
          - el dato es crítico y proviene únicamente de una pista de ledger no reconfirmada
            en esta investigación (`from_ledger_only`).

        Efecto colateral: si detecta caducidad, marca `claim.stale = True` para que el
        informe lo refleje (la caducidad es ortogonal al `VerificationStatus`).
        """
        moment = now or datetime.now(timezone.utc)

        is_stale = self._is_stale(claim, moment)
        if is_stale:
            claim.stale = True

        if claim.is_critical and intent == "use_in_proposal":
            return True
        if is_stale:
            return True
        if claim.is_critical and from_ledger_only:
            return True
        return False

    def _is_stale(self, claim: Claim, now: datetime) -> bool:
        """True si incluso la fuente más reciente del claim supera el umbral de frescura."""
        if not claim.sources:
            return False
        most_recent = max(source.retrieved_at for source in claim.sources)
        return now - most_recent > timedelta(days=self._config.staleness_days)
