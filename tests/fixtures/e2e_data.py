"""Date fixture pentru testele end-to-end (E2E) ale pipeline-ului ACP.

`analiza_test_e2e()` rulează chiar analiza reală (`acp.analiza.analizeaza`)
peste `subiect_test_e2e()` + `comparabile_test_e2e()` — nu construiește un
`Analiza` cu statistici scrise de mână, care ar putea deveni inconsistente
cu comparabilele. Astfel testele de mai jos exercită efectiv filtrarea,
deduplicarea, detectarea outlierilor, statistica și verdictul de poziționare,
exact ca în pipeline-ul real — doar că datele de intrare sunt fixe, nu de
la conectori live.
"""
from __future__ import annotations

from acp.analiza import analizeaza
from acp.modele import Ajustare, Analiza, Comparabila, Subiect


def subiect_test_e2e() -> Subiect:
    """Subiect standard pentru testele E2E: 2 camere, Confort City, 66 mp, 87.000 €."""
    return Subiect(
        pret_eur=87000,
        supr_totala=66,
        supr_utila=61,
        camere=2,
        camere_potential="transformabil în 3",
        etaj=10,
        etaje_total=11,
        an=2009,
        structura="cărămidă",
        incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"],
        locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni",
        coordonate=None,
        parcare="neconfirmat",
        tip_vanzator="persoană fizică",
    )


def comparabile_test_e2e() -> list[Comparabila]:
    """Comparabile realiste, de pe portaluri diferite (date fixe, nu conectori live).

    Suprafețele și vechimea sunt alese să treacă de filtrul de comparabilitate
    (±20% suprafață, ±5 ani vechime față de subiect), astfel încât să rămână
    cu toatele în `analiza.comparabile` după `filtreaza()`.
    """
    return [
        Comparabila(
            sursa="imobiliare.ro", url="https://www.imobiliare.ro/anunt/1",
            pret_eur=89000, supr_totala=65, etaj=9, an=2010,
            dotari=["mobilat"], marcaj="activ", tip="vanzare",
            ajustari=[
                Ajustare(factor="parcare", procent=-0.034,
                          motiv="are parcare, subiectul nu are confirmat"),
            ],
        ),
        Comparabila(
            sursa="storia.ro", url="https://www.storia.ro/anunt/2",
            pret_eur=91000, supr_totala=68, etaj=11, an=2011,
            dotari=["mobilat", "utilat"], marcaj="activ", tip="vanzare", ajustari=[],
        ),
        Comparabila(
            sursa="olx.ro", url="https://www.olx.ro/anunt/3",
            pret_eur=84000, supr_totala=63, etaj=6, an=2008,
            dotari=["semimobilat"], marcaj="activ", tip="vanzare",
            ajustari=[
                Ajustare(factor="etaj", procent=0.02, motiv="etaj mai jos, mai căutat"),
            ],
        ),
        Comparabila(
            sursa="publi24.ro", url="https://www.publi24.ro/anunt/4",
            pret_eur=88500, supr_totala=67, etaj=8, an=2009,
            dotari=["mobilat", "utilat"], marcaj="vandut", tip="vanzare", ajustari=[],
        ),
        Comparabila(
            sursa="romimo.ro", url="https://www.romimo.ro/anunt/5",
            pret_eur=93000, supr_totala=70, etaj=10, an=2012,
            dotari=["mobilat", "utilat", "A/C"], marcaj="activ", tip="vanzare",
            ajustari=[
                Ajustare(factor="parcare", procent=-0.03, motiv="are parcare inclusă"),
            ],
        ),
    ]


def analiza_test_e2e() -> Analiza:
    """Analiză completă pentru test, calculată real din fixture (nu hardcodată)."""
    subiect = subiect_test_e2e()
    comparabile = comparabile_test_e2e()
    return analizeaza(
        subiect,
        comparabile,
        tinta_zile=90,
        surse=["imobiliare.ro", "storia.ro", "olx.ro", "publi24.ro", "romimo.ro"],
    )
