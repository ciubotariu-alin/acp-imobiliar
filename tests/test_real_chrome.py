from acp.connectors import real_chrome


def test_in_challenge_detecteaza_pagina_de_moment():
    assert real_chrome._in_challenge("Doar un moment...") is True
    assert real_chrome._in_challenge("Just a moment...") is True


def test_in_challenge_fals_pe_pagina_reala():
    assert real_chrome._in_challenge("Vânzare apartamente 2 camere Colentina") is False
    assert real_chrome._in_challenge("") is False
    assert real_chrome._in_challenge(None) is False


def test_chrome_disponibil_intoarce_bool():
    # nu lansa browser în test: doar verifică contractul de tip (rezultat cache-uit)
    real_chrome._disponibil_cache = True
    assert real_chrome.chrome_disponibil() is True
    real_chrome._disponibil_cache = False
    assert real_chrome.chrome_disponibil() is False
    real_chrome._disponibil_cache = None  # reset pentru alte teste
