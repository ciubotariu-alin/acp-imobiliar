"""Demo: generează un raport ACP din fixtura de comparabile."""
from acp.modele import Subiect
from acp.connectors.fixture import FixtureConnector
from acp.pipeline import ruleaza

subiect = Subiect(
    pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
    camere_potential="transformabil în 3", etaj=10, etaje_total=11, an=2009,
    structura="cărămidă", incalzire="centrală proprie de apartament",
    dotari=["mobilat", "utilat", "A/C"],
    locatie="Confort City, Splaiul Unirii 9", zona_reala="limită Popești-Leordeni",
    parcare="neconfirmat", tip_vanzator="persoană fizică",
)

narativ = {
    "recomandare": "menține prețul de listare la 87.000 € și testează plafonul 30 de zile, apoi coboară controlat.",
    "faze": [
        {"nume": "Faza 1 — Testare plafon", "zile": "0–30", "pret": "87.000 €",
         "obiectiv": "prinde cumpărătorul premium", "prag": "≥6 vizionări → menții"},
        {"nume": "Faza 2 — Calibrare", "zile": "31–60", "pret": "84.900 €",
         "obiectiv": "sub pragul de 85k", "prag": "≥1 ofertă serioasă → negociezi"},
        {"nume": "Faza 3 — Finalizare", "zile": "61–90", "pret": "82.500 €",
         "obiectiv": "declanșezi ezitanții", "prag": "accepți oferte 81–83k"},
    ],
    "anunt": {"titlu": "2 camere Confort City, Splaiul Unirii 9 — complet mobilat, etaj înalt",
              "descriere": "Apartament gata de mutare, luminos, centrală proprie. Comision 0% cumpărător."},
}

conn = FixtureConnector("exemple/comparabile_confort_city.json")
analiza = ruleaza(subiect, [conn], tinta_zile=90,
                  cale_pdf="output/ACP_ConfortCity_90zile.pdf", narativ=narativ)
print(f"Raport generat. Încadrare: {analiza.incadrare}, "
      f"poziționare {analiza.pozitionare_pct:+.1f}% față de mediană.")
print("PDF: output/ACP_ConfortCity_90zile.pdf")
