import pytest
from acp.statistica import calculeaza_statistici


def test_statistici_de_baza():
    s = calculeaza_statistici([999, 1101, 1275, 1308, 1369])
    assert s.n == 5
    assert s.minim == 999
    assert s.maxim == 1369
    assert s.mediana == 1275


def test_statistici_par():
    s = calculeaza_statistici([1000, 1200])
    assert s.mediana == pytest.approx(1100)


def test_statistici_gol_ridica_eroare():
    with pytest.raises(ValueError):
        calculeaza_statistici([])
