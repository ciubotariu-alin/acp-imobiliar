from acp.modele import Comparabila
from acp.context import calculeaza_context


def _active(n):
    return [Comparabila(sursa="s", pret_eur=85000, supr_totala=65) for _ in range(n)]


def test_oferta_mica_piata_vanzatorului():
    ctx = calculeaza_context(_active(3))
    assert ctx.nr_active == 3
    assert ctx.tensiune == "piata_vanzatorului"


def test_oferta_mare_piata_cumparatorului():
    ctx = calculeaza_context(_active(20))
    assert ctx.tensiune == "piata_cumparatorului"


def test_oferta_medie_echilibrata():
    ctx = calculeaza_context(_active(10))
    assert ctx.tensiune == "echilibrata"


def test_days_on_market_mediat():
    ctx = calculeaza_context(_active(10), days_on_market=[30, 60, 90])
    assert ctx.days_on_market_med == 60
