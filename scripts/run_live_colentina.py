"""Rulare live ACP pe subiectul Colentina (id 275238880), tinta 45 zile.

Reproduce fidel fluxul din PipelineOrchestrator.deduplicate_and_analyze(dedup_poze=True),
dar cu tinta_zile=45 si cu raportare explicita a ce se elimina (subiect vs duplicate).
"""
import logging
from pathlib import Path

from acp.core.pipeline import PipelineOrchestrator
from acp.modele import Subiect, CriteriiCautare
from acp.filtrare import filtreaza, dedup
from acp.detalii import imbogateste_detalii
from acp.cache_detalii import CacheDetalii
from acp.cache_hashuri import CacheHashuri
from acp.dedup_poze import confirma_si_dedup
from acp.poze_fetch import construieste_fetch_poze, hashuri_din_urls
from acp.connectors import detaliu_fetch
from acp.connectors.imobiliare import USER_AGENT as UA
from acp.analiza import analizeaza
from acp.raport.render import scrie_pdf

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SUBIECT_URL = "https://www.imobiliare.ro/oferta/apartament-de-vanzare-sector-2-colentina-mobilat-2-camere-275238880"

subiect = Subiect(
    pret_eur=108000, supr_totala=59, supr_utila=54, camere=2,
    etaj=2, etaje_total=10, an=1980,
    structura="panou", incalzire="termoficare", stare="bun",
    dotari=["mobilat", "utilat"],
    locatie="Sector 2, Colentina", zona_reala="Colentina",
    tip_vanzator="agentie", url=SUBIECT_URL,
)

criterii = CriteriiCautare(
    camere=2, supr_min=round(59 * 0.8), supr_max=round(59 * 1.2),
    zona="colentina", raza_km=1.5,
)

print("\n" + "=" * 72)
print(f"LIVE ACP — Colentina — subiect {subiect.pret_eur:,.0f}€ / {subiect.supr_totala:.0f}mp / "
      f"{subiect.camere}cam / etaj {subiect.etaj} — tinta 45 zile")
print("=" * 72 + "\n")

orch = PipelineOrchestrator()

# 1. Fetch brut din toti connectorii
comparabile = orch.fetch_comparabile_paralel(subiect, criterii)
print(f"\n>> {len(comparabile)} comparabile brute din surse: "
      f"{sorted({c.sursa for c in comparabile})}\n")

# 2. Replica deduplicate_and_analyze(dedup_poze=True), dar cu tinta=45 + raportare
vanzari = [c for c in comparabile if c.tip == "vanzare"]
survivors = filtreaza(subiect, dedup(vanzari))
print(f">> {len(survivors)} supravietuiesc filtrarii (supr +/-20%, an +/-5)\n")

fetchers = {c.name: c.fetch_detaliu for c in orch.connectors if hasattr(c, "fetch_detaliu")}
n = imbogateste_detalii(survivors, fetchers, CacheDetalii())
print(f">> {n}/{len(survivors)} imbogatite cu detalii+poze de pe pagina de detaliu\n")

# 3. Poze subiect (imobiliare — poate esua daca Cloudflare blocheaza)
subiect_hashes = []
if subiect.url:
    _, poze_subiect = detaliu_fetch.fetch_detaliu(subiect.url, UA)
    subiect_hashes = hashuri_din_urls(poze_subiect, UA)
print(f">> Poze subiect obtinute: {len(subiect_hashes)} hash-uri "
      f"({'OK' if subiect_hashes else 'ESUAT — probabil Cloudflare 403'})\n")

fetch_poze = construieste_fetch_poze(UA, cache=CacheHashuri())
fallback_metadata = subiect.url is None
if subiect.url and not subiect_hashes:
    print(">> [fix] URL subiect dat dar pozele n-au putut fi luate -> "
          "NU exclud agresiv pe metadata (pastrez comparabilele)\n")

pastrate, dup_elim, subj_elim = confirma_si_dedup(
    survivors, subiect, subiect_hashes, fetch_poze,
    fallback_metadata_subiect=fallback_metadata,
)

print(f">> DEDUP PE POZE:")
print(f"   - {len(subj_elim)} instante ale SUBIECTULUI eliminate")
for c in subj_elim:
    print(f"       SUBIECT  {c.sursa:14} {c.pret_eur:>10,.0f}€ {c.supr_totala:.0f}mp  {c.url}")
print(f"   - {len(dup_elim)} DUPLICATE cross-agentie eliminate")
for c in dup_elim:
    print(f"       DUPLICAT {c.sursa:14} {c.pret_eur:>10,.0f}€ {c.supr_totala:.0f}mp  {c.url}")
print()

elim = {id(c) for c in dup_elim} | {id(c) for c in subj_elim}
comparabile_curate = [c for c in comparabile if id(c) not in elim]

analiza = analizeaza(subiect, comparabile_curate, tinta_zile=45,
                     surse=sorted({c.sursa for c in comparabile_curate}))

print(f">> ANALIZA (tinta 45 zile):")
print(f"   Comparabile in analiza: {analiza.stat_ajustat.n}")
print(f"   Mediana ajustata: {analiza.stat_ajustat.mediana:,.0f} €/mp")
print(f"   Incadrare: {analiza.incadrare} | pozitionare {analiza.pozitionare_pct:+.1f}%")
print(f"   Pret listare recomandat: {analiza.pret_listare[0]:,.0f}–{analiza.pret_listare[1]:,.0f} €")
print(f"   Pret tranzactie estimat: {analiza.pret_tranzactie[0]:,.0f}–{analiza.pret_tranzactie[1]:,.0f} €\n")

Path("output").mkdir(exist_ok=True)
pdf = "output/ACP_Colentina_45zile_LIVE.pdf"
scrie_pdf(analiza, pdf, narativ={"tinta_zile": 45, "strategy": "Vanzare tinta in 45 de zile"})
print(f">> PDF: {pdf}\n")
