"""Interfața comună pentru toți connectorii de portal."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from acp.modele import CriteriiCautare, Comparabila


@runtime_checkable
class Connector(Protocol):
    nume: str

    def cauta(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Caută comparabile pe portal după criterii și le întoarce normalizate."""
        ...
