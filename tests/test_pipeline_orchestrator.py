"""Tests for PipelineOrchestrator.deduplicate_and_analyze's imbogateste toggle (Task 12).

Deliberately does NOT import `acp.pipeline` (Plan 1 schelet), which pulls in
`acp.raport.render` -> WeasyPrint at import time. This file only needs
`acp.core.pipeline.PipelineOrchestrator`, so it runs fine in environments
without WeasyPrint installed (unlike tests/test_pipeline.py).
"""
import pytest

from acp.modele import Subiect
from acp.core.pipeline import PipelineOrchestrator


@pytest.fixture
def subiect_test():
    """Test subject fixture."""
    return Subiect(
        pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
        camere_potential="transformabil în 3", etaj=10, etaje_total=11,
        an=2009, structura="cărămidă", incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"], locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni", coordonate=None,
        parcare="neconfirmat", tip_vanzator="persoană fizică",
    )


@pytest.fixture
def orchestrator():
    """PipelineOrchestrator fixture."""
    return PipelineOrchestrator()


def test_deduplicate_and_analyze_imbogateste_aplica_dotari(orchestrator, subiect_test, tmp_path):
    from acp.modele import Comparabila
    from acp.cache_detalii import CacheDetalii

    # subiectul are mobilat; comparabilele NU au detalii inițial
    subiect_test.dotari = ["mobilat"]
    comps = [
        Comparabila(sursa="imobiliare.ro", pret_eur=95000.0, supr_totala=64.0,
                    url="https://imobiliare.ro/a", an=2010, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=99000.0, supr_totala=66.0,
                    url="https://imobiliare.ro/b", an=2011, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=90000.0, supr_totala=62.0,
                    url="https://imobiliare.ro/c", an=2009, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=102000.0, supr_totala=68.0,
                    url="https://imobiliare.ro/d", an=2012, marcaj="activ"),
    ]
    # toate conectorii orchestratorului primesc un fetch_detaliu_text care spune "fără dotări"
    for conn in orchestrator.connectors:
        conn.fetch_detaliu_text = lambda url: "apartament nefinisat, structură beton"

    cache = CacheDetalii(dir=str(tmp_path / "d"))
    analiza = orchestrator.deduplicate_and_analyze(
        subiect_test, comps, imbogateste=True, cache=cache
    )
    # comparabilele din analiză au fost îmbogățite (detalii_complete True)
    assert all(c.detalii_complete for c in analiza.comparabile)
    # subiectul are mobilat, comparabilele nu → fiecare primește ajustare mobilat +4%
    assert any(any(a.factor == "mobilat" for a in c.ajustari) for c in analiza.comparabile)


def test_deduplicate_and_analyze_fara_imbogatire_nu_ajusteaza_dotari(orchestrator, subiect_test):
    from acp.modele import Comparabila
    subiect_test.dotari = ["mobilat"]
    comps = [
        Comparabila(sursa="imobiliare.ro", pret_eur=95000.0, supr_totala=64.0, an=2010, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=99000.0, supr_totala=66.0, an=2011, marcaj="activ"),
    ]
    analiza = orchestrator.deduplicate_and_analyze(subiect_test, comps, imbogateste=False)
    # fără îmbogățire, nicio comparabilă nu are detalii_complete → nicio ajustare de mobilat
    assert not any(any(a.factor == "mobilat" for a in c.ajustari) for c in analiza.comparabile)
