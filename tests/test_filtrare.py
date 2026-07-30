from acp.modele import Subiect, Comparabila
from acp.filtrare import filtreaza, dedup, marcheaza_outlieri


def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009, locatie="Confort City")


def _comp(pret, supr, an=2009, etaj=None, sursa="storia"):
    return Comparabila(sursa=sursa, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, an=an, dotari=[])


def test_filtreaza_dupa_suprafata():
    comps = [_comp(85000, 65), _comp(85900, 86)]  # 86mp = +30% > 20%
    rezultat = filtreaza(_subiect(), comps)
    suprafete = {c.supr_totala for c in rezultat}
    assert 65 in suprafete and 86 not in suprafete


def test_filtreaza_dupa_vechime():
    comps = [_comp(85000, 65, an=2009), _comp(85000, 65, an=1985)]
    rezultat = filtreaza(_subiect(), comps)
    ani = {c.an for c in rezultat}
    assert 2009 in ani and 1985 not in ani


def test_dedup_elimina_duplicate():
    a = _comp(85000, 65, etaj=10, an=2008, sursa="storia")
    b = _comp(85000, 65, etaj=10, an=2008, sursa="olx")  # aceeași proprietate, alt portal
    c = _comp(89000, 65, etaj=3, an=2009, sursa="publi24")
    rezultat = dedup([a, b, c])
    assert len(rezultat) == 2


def test_marcheaza_outlieri():
    comps = [_comp(p * 65 / 1000, 65) for p in [1101, 1275, 1308, 1369, 300]]
    pastrate, outlieri = marcheaza_outlieri(comps)
    assert len(outlieri) == 1
    assert outlieri[0].euro_mp < 500
