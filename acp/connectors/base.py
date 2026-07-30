"""Interfață comună pentru connectori de portaluri."""
from abc import ABC, abstractmethod

from acp.modele import CriteriiCautare, Comparabila


class ConnectorError(Exception):
    """Eroare la extragere date de pe portal."""

    def __init__(self, message: str, connector: str | None = None):
        super().__init__(message)
        self.connector = connector


class ConnectorBase(ABC):
    """Interfață comună pentru toți connectorii."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Caută anunțuri pe portal conform criteriilor.

        Args:
            criterii: CriteriiCautare cu camere, suprafață, zonă, rază

        Returns:
            Listă de Comparabila (gol dacă nimic găsit sau connector blocat)

        Raises:
            ConnectorError: dacă search eșuează (timeout, 403, etc)
        """
        pass
