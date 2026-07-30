"""Connector de test: citește comparabile dintr-un fișier JSON."""
from __future__ import annotations

import json

from acp.modele import CriteriiCautare, Comparabila


class FixtureConnector:
    nume = "fixture"

    def __init__(self, cale_json: str):
        self.cale_json = cale_json

    def cauta(self, criterii: CriteriiCautare) -> list[Comparabila]:
        with open(self.cale_json, encoding="utf-8") as f:
            date = json.load(f)
        return [Comparabila(**d) for d in date]
