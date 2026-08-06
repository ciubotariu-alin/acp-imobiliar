"""Smoke test: pipeline-ul REAL (PipelineOrchestrator) pe imobiliare, cu Chrome real.

Rulează cu: ACP_REAL_CHROME=1 DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python smoke_pipeline_realchrome.py
Dovedește că produsul în sine (nu scriptul ad-hoc) trece de Cloudflare pe imobiliare.
"""
import logging
from acp.core.pipeline import PipelineOrchestrator
from acp.modele import Subiect, CriteriiCautare

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SUBIECT_URL = "https://www.imobiliare.ro/oferta/apartament-de-vanzare-sector-2-colentina-mobilat-2-camere-275238880"
subiect = Subiect(
    pret_eur=108000, supr_totala=59, supr_utila=54, camere=2, etaj=2, etaje_total=8, an=1980,
    structura="panou", incalzire="termoficare", stare="bun", dotari=["mobilat", "utilat"],
    locatie="Sector 2, Colentina", zona_reala="Colentina", tip_vanzator="agentie", url=SUBIECT_URL,
)
criterii = CriteriiCautare(camere=2, supr_min=47, supr_max=71, zona="colentina", raza_km=1.5)

orch = PipelineOrchestrator()
comparabile = orch.fetch_comparabile_paralel(subiect, criterii)
surse = {}
for c in comparabile:
    surse[c.sursa] = surse.get(c.sursa, 0) + 1
print(f"\n>> BRUTE: {len(comparabile)} din {surse}")
imob_ids = {(c.url or "").split("-")[-1] for c in comparabile if c.sursa == "imobiliare.ro"}
print(f">> imobiliare via Chrome real: subiect 275238880 in brute? {'275238880' in imob_ids} | "
      f"geaman 275736626 in brute? {'275736626' in imob_ids}")

analiza = orch.deduplicate_and_analyze(subiect, comparabile, imbogateste=True, dedup_poze=True)

ids_finale = {(c.url or "").split("-")[-1] for c in analiza.comparabile} | \
             {(c.url or "").split("-")[-1] for c in analiza.outlieri}
print(f"\n>> DUPA DEDUP+ANALIZA:")
print(f"   comparabile in analiza: {analiza.stat_ajustat.n}")
print(f"   subiect 275238880 mai e in set? {'275238880' in ids_finale}  (asteptat: False)")
print(f"   geaman 275736626 mai e in set? {'275736626' in ids_finale}  (asteptat: False)")
print(f"   surse in analiza: {sorted({c.sursa for c in analiza.comparabile})}")
print(f"   mediana ajustata: {analiza.stat_ajustat.mediana:,.0f} €/mp | incadrare: {analiza.incadrare}")
