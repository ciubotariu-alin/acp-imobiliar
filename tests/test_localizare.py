import pytest
from acp.core.localizare import normalizeaza_zona


def test_normalizeaza_zona_confort_city():
    """Normalizare loc 'Confort City, Splaiul Unirii 9' → zone label."""
    result = normalizeaza_zona(
        locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni"
    )
    assert result["zona_eticheta"] == "Viștei"  # cartier de referință
    assert result["raza_km"] == 1.5
    assert "coordonate" in result


def test_normalizeaza_zona_sector_3():
    """Normalizare sector 3 generic."""
    result = normalizeaza_zona(locatie="Sector 3", zona_reala="Vitan-Bârzești")
    assert result["zona_eticheta"] == "Vitan"
    assert result["raza_km"] == 1.5


def test_normalizeaza_zona_necunoscuta():
    """Normalizare zonă necunoscută — fallback generic."""
    result = normalizeaza_zona(locatie="Zona X", zona_reala=None)
    assert result["zona_eticheta"] == "generic"
    assert result["raza_km"] >= 1.0
