"""Orchestrarea end-to-end: subiect + connectori → analiză → PDF."""
from __future__ import annotations

from acp.modele import Subiect, CriteriiCautare, Comparabila, Analiza
from acp.connectors.base import Connector
from acp.analiza import analizeaza
from acp.raport.render import scrie_pdf


def criterii_din_subiect(subiect: Subiect, prag_supr: float = 0.20,
                         raza_km: float = 1.5) -> CriteriiCautare:
    return CriteriiCautare(
        camere=subiect.camere,
        supr_min=subiect.supr_totala * (1 - prag_supr),
        supr_max=subiect.supr_totala * (1 + prag_supr),
        an_min=(subiect.an - 5) if subiect.an else None,
        an_max=(subiect.an + 5) if subiect.an else None,
        zona=subiect.zona_reala or subiect.locatie,
        raza_km=raza_km,
    )


def ruleaza(subiect: Subiect, connectori: list[Connector], tinta_zile: int,
            cale_pdf: str, narativ: dict | None = None) -> Analiza:
    criterii = criterii_din_subiect(subiect)
    comparabile: list[Comparabila] = []
    for conn in connectori:
        try:
            gasite = conn.cauta(criterii)
            comparabile.extend(gasite)
        except Exception as e:  # un connector căzut nu blochează restul
            print(f"[avertisment] connectorul '{getattr(conn, 'nume', '?')}' a eșuat: {e}")
    # `surse` nu se mai suprapune peste conn.nume: analizeaza() derivă lista de
    # portaluri direct din câmpul `sursa` al fiecărei comparabile găsite, ceea ce
    # reflectă corect proveniența datelor chiar și atunci când un singur connector
    # (ex. FixtureConnector) agregă comparabile din mai multe portaluri simulate.
    analiza = analizeaza(subiect, comparabile, tinta_zile=tinta_zile)
    scrie_pdf(analiza, cale_pdf, narativ)
    return analiza
