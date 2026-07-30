from acp.modele import CriteriiCautare
from acp.connectors.fixture import FixtureConnector


def test_fixture_incarca_comparabile():
    conn = FixtureConnector("exemple/comparabile_confort_city.json")
    crit = CriteriiCautare(camere=2, supr_min=55, supr_max=80, zona="Confort City")
    rezultat = conn.search(crit)
    assert conn.name == "fixture"
    assert len(rezultat) == 6
    assert rezultat[0].sursa == "storia"
