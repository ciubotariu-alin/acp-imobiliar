from acp.modele import Subiect
from acp.connectors.fixture import FixtureConnector
from acp.pipeline import criterii_din_subiect, ruleaza


def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                   locatie="Confort City")


def test_criterii_din_subiect():
    crit = criterii_din_subiect(_subiect())
    assert crit.camere == 2
    assert crit.supr_min < 66 < crit.supr_max


def test_pipeline_end_to_end(tmp_path):
    cale = tmp_path / "raport.pdf"
    conn = FixtureConnector("exemple/comparabile_confort_city.json")
    analiza = ruleaza(_subiect(), [conn], tinta_zile=90, cale_pdf=str(cale))
    assert cale.exists()
    assert cale.read_bytes()[:4] == b"%PDF"
    assert analiza.stat_ajustat.n >= 3
    assert "storia" in analiza.surse
