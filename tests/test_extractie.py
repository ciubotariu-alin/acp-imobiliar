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


def test_parcare_owned_wins_over_negation():
    """Regression: explicit owned keywords should win over _PARCARE_LIPSA."""
    assert extrage_parcare("apartament cu garaj propriu, fără parcare pentru oaspeți") == "owned"


def test_parcare_resedinta_wins_over_negation():
    """Regression: explicit reședință keywords should win over _PARCARE_LIPSA."""
    assert extrage_parcare("loc de reședință închiriat de la primărie, fără parcare pentru oaspeți") == "resedinta"


def test_parcare_generic_no_info_not_masked():
    """Regression: bare 'fără mențiune' (generic no-info) should not mask explicit owned."""
    assert extrage_parcare("apartament fără mențiune despre încălzire, are parcare proprie") == "owned"


def test_extrage_dotari_detecteaza_etichete_canonice():
    from acp.extractie import extrage_dotari
    text = "Apartament mobilat, aer condiționat, 2 balcoane, boxă la subsol"
    d = extrage_dotari(text)
    assert "mobilat" in d
    assert "aer condiționat" in d
    assert "balcon" in d
    assert "boxă" in d


def test_extrage_dotari_gol_cand_lipsesc():
    from acp.extractie import extrage_dotari
    assert extrage_dotari("apartament 2 camere, etaj 3") == []


def test_extrage_dotari_utilat_conteaza_ca_mobilat():
    from acp.extractie import extrage_dotari
    # KW_MOBILAT = ["mobilat", "utilat"] → eticheta canonică "mobilat"
    assert "mobilat" in extrage_dotari("complet utilat")


def test_extrage_etaje_total_din_regim_inaltime():
    from acp.extractie import extrage_etaje_total
    assert extrage_etaje_total("Regim înălțime: P+8E") == 8
    assert extrage_etaje_total("bloc P+4E cu lift") == 4


def test_extrage_etaje_total_lipsa():
    from acp.extractie import extrage_etaje_total
    assert extrage_etaje_total("apartament fără mențiune de regim") is None
