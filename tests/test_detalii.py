from acp.detalii import parseaza_detaliu


def test_parseaza_detaliu_extrage_toate_campurile():
    text = (
        "Apartament renovat, structură beton, centrală proprie, mobilat, "
        "aer condiționat, balcon. Garaj subteran inclus. Regim înălțime: P+8E"
    )
    d = parseaza_detaliu(text, an=2015)
    assert d["structura"] == "beton"
    assert d["incalzire"] == "centrala_proprie"
    assert d["stare"] == "renovat"
    assert d["stare_incredere"] > 0.5
    assert d["parcare_tip"] == "owned"
    assert "mobilat" in d["dotari"]
    assert "balcon" in d["dotari"]
    assert d["etaje_total"] == 8


def test_parseaza_detaliu_camp_necunoscut_none():
    d = parseaza_detaliu("apartament 2 camere", an=None)
    assert d["structura"] is None
    assert d["stare"] is None
    assert d["dotari"] == []
    assert d["etaje_total"] is None
