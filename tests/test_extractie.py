from acp.extractie import (
    extrage_structura, extrage_incalzire, extrage_stare, extrage_parcare,
)


def test_structura_detecteaza_caramida_si_panou():
    assert extrage_structura("apartament în bloc de cărămidă") == "caramida"
    assert extrage_structura("bloc din panou prefabricat") == "panou"
    assert extrage_structura("structura beton, cadre") == "beton"
    assert extrage_structura("bloc BCA") == "bca"
    assert extrage_structura("fără mențiune") is None


def test_incalzire_detecteaza_tipurile():
    assert extrage_incalzire("are centrală proprie de apartament") == "centrala_proprie"
    assert extrage_incalzire("racordat la termoficare") == "termoficare"
    assert extrage_incalzire("centrală de bloc") == "centrala_bloc"
    assert extrage_incalzire("nimic relevant") is None


def test_stare_renovat_are_incredere_peste_prag():
    stare, incredere = extrage_stare("apartament complet renovat recent")
    assert stare == "renovat"
    assert incredere > 0.5


def test_stare_marketing_are_incredere_sub_prag():
    # "lux"/"premium" = limbaj de marketing → nu declanșează ajustare
    stare, incredere = extrage_stare("apartament de lux, finisaje premium")
    assert stare == "renovat"
    assert incredere <= 0.5


def test_stare_necesita_renovare():
    stare, incredere = extrage_stare("necesită renovare completă")
    assert stare == "necesita_renovare"
    assert incredere > 0.5


def test_stare_ambigua_none():
    stare, incredere = extrage_stare("apartament 2 camere, etaj 3")
    assert stare is None
    assert incredere == 0.0


def test_parcare_owned_explicit():
    assert extrage_parcare("include garaj subteran", an=2015) == "owned"
    assert extrage_parcare("parcare proprie inclusă în preț") == "owned"


def test_parcare_resedinta_explicit():
    assert extrage_parcare("loc de reședință închiriat de la primărie") == "resedinta"


def test_parcare_ambigua_heuristica_pe_vechime():
    assert extrage_parcare("loc de parcare", an=2015) == "owned"
    assert extrage_parcare("loc de parcare", an=1985) == "resedinta"
    assert extrage_parcare("loc de parcare", an=2004) is None
    assert extrage_parcare("loc de parcare") is None


def test_parcare_lipsa_none_string():
    assert extrage_parcare("apartament fără nicio mențiune de parcare") == "none"
