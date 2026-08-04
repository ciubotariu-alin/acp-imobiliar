"""Normalizare zone și parametri căutare."""


def normalizeaza_zona(locatie: str, zona_reala: str | None = None) -> dict:
    """
    Convertește locație + zona reală în parametri de căutare standardizați.

    Args:
        locatie: descriere anunț (ex. "Confort City, Splaiul Unirii 9")
        zona_reala: localizare precisă din coordonate/agent (ex. "limită Popești")

    Returns:
        dict cu zona_eticheta, raza_km, coordonate (lat, lng dacă available)
    """
    # Mapare locații cunoscute la zone/cartiere
    locatii_map = {
        "confort city": "Viștei",
        "splaiul unirii": "Viștei",
    }

    # Mapare zone reale la cartiere
    zone_reale_map = {
        "vitan": "Vitan",
        "vitan-bârzești": "Vitan",
        "sector 3": "Vitan",
    }

    # Prioritizare zona_reala peste locatie
    zona_eticheta = None
    raza_km = 1.5

    # Verific zona_reala mai întâi
    if zona_reala:
        zona_normalized = zona_reala.lower().strip()
        for key, value in zone_reale_map.items():
            if key in zona_normalized:
                zona_eticheta = value
                break

    # Dacă nu am găsit din zona_reala, verific locatie
    if not zona_eticheta and locatie:
        locatie_normalized = locatie.lower().strip()
        for key, value in locatii_map.items():
            if key in locatie_normalized:
                zona_eticheta = value
                break

        # Verific și sector în locatie
        if not zona_eticheta:
            for key, value in zone_reale_map.items():
                if key in locatie_normalized:
                    zona_eticheta = value
                    break

    # Fallback generic
    if not zona_eticheta:
        zona_eticheta = "generic"
        raza_km = 1.0

    return {
        "zona_eticheta": zona_eticheta,
        "raza_km": raza_km,
        "coordonate": None,
    }
