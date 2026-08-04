"""Connector de test: citește comparabile dintr-un fișier JSON."""
from __future__ import annotations

import json

from acp.connectors.base import ConnectorBase
from acp.modele import CriteriiCautare, Comparabila


class FixtureConnector(ConnectorBase):
    """Connector fixture pentru test: citește comparabile dintr-un fișier JSON."""

    def __init__(self, cale_json: str):
        super().__init__(name="fixture")
        self.cale_json = cale_json

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        with open(self.cale_json, encoding="utf-8") as f:
            date = json.load(f)
        return [Comparabila(**d) for d in date]
