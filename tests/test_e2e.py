"""Test end-to-end (E2E) al pipeline-ului ACP, cu date fixture (nu conectori live).

Verifică fluxul complet: Subiect + Comparabile → analiza reală
(`acp.analiza.analizeaza`) → randare HTML/PDF (`acp.raport.render`).

Notă: brief-ul de task menționează `render_pdf_report(analiza, output_dir=...)`,
dar funcția reală din `acp/raport/render.py` este `scrie_pdf(analiza, cale_pdf,
narativ=None) -> None`, care scrie direct la o cale de fișier și nu întoarce
nimic. Testele de mai jos folosesc semnătura reală.
"""
from __future__ import annotations

from acp.raport.render import construieste_html, scrie_pdf
from tests.fixtures.e2e_data import analiza_test_e2e, comparabile_test_e2e, subiect_test_e2e


def test_e2e_analiza_produce_toate_campurile():
    """Analiza E2E (rulată real peste fixture) are toate câmpurile populate corect."""
    analiza = analiza_test_e2e()

    # Comparabilele au trecut de filtrare/dedup/outlieri — cel mult câte au intrat.
    assert len(analiza.comparabile) > 0
    assert len(analiza.comparabile) + len(analiza.outlieri) <= len(comparabile_test_e2e())

    # Prețul subiectului e pozitiv, calculat pe suprafața totală.
    assert analiza.subiect.euro_mp > 0
    assert analiza.subiect.euro_mp == analiza.subiect.pret_eur / analiza.subiect.supr_totala

    # Statistici brute și ajustate valide.
    assert analiza.stat_brut.n > 0
    assert analiza.stat_ajustat.n > 0
    assert analiza.stat_ajustat.minim <= analiza.stat_ajustat.mediana <= analiza.stat_ajustat.maxim

    # Benzile de preț sunt ordonate corect (limită inferioară < superioară).
    assert analiza.pret_listare[0] < analiza.pret_listare[1]
    assert analiza.pret_tranzactie[0] < analiza.pret_tranzactie[1]
    # Corecția anunț→tranzacție trage prețul de tranzacționare sub cel de listare.
    assert analiza.pret_tranzactie[1] <= analiza.pret_listare[1]

    # Încadrarea reflectă poziționarea calculată (subiect vs. mediană ajustată).
    assert analiza.incadrare in {"sub piață", "corect", "supraevaluat"}
    if analiza.pozitionare_pct > 5:
        assert analiza.incadrare == "supraevaluat"
    elif analiza.pozitionare_pct < -5:
        assert analiza.incadrare == "sub piață"
    else:
        assert analiza.incadrare == "corect"

    # Context de piață și surse populate.
    assert analiza.context.nr_active > 0
    assert set(analiza.surse) == {"imobiliare.ro", "storia.ro", "olx.ro", "publi24.ro", "romimo.ro"}
    assert analiza.tinta_zile == 90


def test_e2e_html_contine_datele_cheie():
    """HTML-ul randat conține adresa subiectului, statisticile €/mp și disclaimerul."""
    analiza = analiza_test_e2e()
    subiect = subiect_test_e2e()

    html = construieste_html(analiza)

    assert subiect.locatie in html
    assert "€/mp" in html
    assert f"{analiza.tinta_zile}" in html
    # Disclaimerul obligatoriu (nu e evaluare ANEVAR).
    assert "ANEVAR" in html


def test_e2e_render_pdf_output(tmp_path):
    """Randare PDF completă din Analiza E2E — fișier PDF valid, cu conținut real."""
    analiza = analiza_test_e2e()
    cale_pdf = tmp_path / "ACP_ConfortCity_e2e.pdf"

    scrie_pdf(analiza, str(cale_pdf))

    assert cale_pdf.exists()
    assert cale_pdf.suffix == ".pdf"

    date = cale_pdf.read_bytes()
    assert date[:4] == b"%PDF"
    # PDF-ul e non-trivial (conține tabele, stiluri, text real, nu doar un antet gol).
    assert cale_pdf.stat().st_size > 10000
