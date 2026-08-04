#!/usr/bin/env python3
"""Test live ACP pipeline pe un anunț real și generare PDF."""

from pathlib import Path
from acp.core.pipeline import PipelineOrchestrator
from acp.modele import Subiect, CriteriiCautare
from acp.raport.render import scrie_pdf


def test_live_subject(tinta_zile: int = 90):
    """Test pipeline pe un anunț real (exemple din Viștei, București)."""

    # ============ 1. DEFINIȚI PROPRIETATEA DE ANALIZAT ============
    subiect = Subiect(
        pret_eur=95000,           # Prețul anunțului
        supr_totala=70,           # Suprafață totală
        supr_utila=64,            # Suprafață utilă
        camere=2,                 # Camere
        camere_potential="transformabil în 3",
        etaj=4,
        etaje_total=8,
        an=2005,
        structura="cărămidă",
        incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "AC", "loc parcare"],
        locatie="Viștei, București",
        zona_reala="Viștei",
        parcare="loc parcare inclus",
        tip_vanzator="persoană fizică",
    )

    # ============ 2. DEFINIȚI CRITERII DE CĂUTARE PENTRU COMPARABILE ============
    criterii = CriteriiCautare(
        camere=2,
        supr_min=60,        # ±20% din 70 → 56-84
        supr_max=84,
        zona="Viștei",
        raza_km=1.5,        # Rază 1.5 km
    )

    print(f"\n{'='*70}")
    print(f"TESTARE LIVE ACP PIPELINE")
    print(f"{'='*70}\n")

    print(f"📍 SUBIECT:")
    print(f"   Preț: €{subiect.pret_eur:,.0f}")
    print(f"   Suprafață: {subiect.supr_totala} m² total / {subiect.supr_utila} m² utilă")
    print(f"   Camere: {subiect.camere}")
    print(f"   Localitate: {subiect.zona_reala}")
    print(f"   Euro/mp: €{subiect.euro_mp:,.0f}/mp\n")

    print(f"🔍 CRITERIILE DE CĂUTARE:")
    print(f"   Camere: {criterii.camere}")
    print(f"   Suprafață: {criterii.supr_min}-{criterii.supr_max} m²")
    print(f"   Zona: {criterii.zona}")
    print(f"   Rază: {criterii.raza_km} km\n")

    # ============ 3. RULAȚI ORCHESTRATOR ============
    print(f"⏳ Se caută comparabile din 9 conectori...")
    print(f"   (imobiliare.ro, historia.ro, olx.ro, publi24.ro, romimo.ro, etc.)\n")

    orchestrator = PipelineOrchestrator()

    try:
        # Fetch din toți connectorii în paralel
        comparabile = orchestrator.fetch_comparabile_paralel(subiect, criterii)
        print(f"✅ Găsite {len(comparabile)} comparabile brute\n")

        if not comparabile:
            print("⚠️  Nu s-au găsit comparabile. Posibil:")
            print("   - Portalurile sunt DOWN")
            print("   - Zona nu are anunțuri active")
            print("   - Criterii prea restrictive")
            return

        # Afișează primele 5
        print(f"📊 PRIMELE 5 COMPARABILE:")
        for i, comp in enumerate(comparabile[:5], 1):
            price_str = f"€{comp.pret_eur:,.0f}" if comp.pret_eur else "N/A"
            euro_mp = f"€{comp.euro_mp:,.0f}/mp" if comp.euro_mp else "N/A"
            print(f"   {i}. {comp.sursa:15} | {price_str:12} | {comp.supr_totala:5.0f}m² | {euro_mp}")
        print()

        # ============ 4. ANALIZĂ ============
        print(f"🔬 Se deduplică și analizează...\n")
        analiza = orchestrator.deduplicate_and_analyze(subiect, comparabile)

        print(f"📈 REZULTATE ANALIZĂ:")
        print(f"   Total inițial: {len(comparabile)} anunțuri")
        print(f"   După filtrare: {analiza.stat_ajustat.n} comparabile valide")
        print(f"   Mediana pe piață: €{analiza.stat_ajustat.mediana:,.0f}")
        print(f"   Range: €{analiza.stat_ajustat.minim:,.0f} - €{analiza.stat_ajustat.maxim:,.0f}\n")

        print(f"💰 ESTIMARE PREȚ:")
        print(f"   Preț subiect: €{subiect.pret_eur:,.0f}")
        print(f"   Recomandare: €{analiza.pret_estimat_eur:,.0f}")
        delta = ((analiza.pret_estimat_eur / subiect.pret_eur) - 1) * 100
        direction = "👆 SCUMP" if delta > 0 else "👇 IEFTIN" if delta < 0 else "✓ CORECT"
        print(f"   Delta: {delta:+.1f}% {direction}\n")

        print(f"📍 CONTEXT PIAȚĂ:")
        print(f"   Anunțuri active: {analiza.context_piata.nr_active}")
        print(f"   Tensiune: {analiza.context_piata.tensiune}")
        print(f"   Zile pe piață (mediana): {analiza.context_piata.days_on_market_med or 'N/A'}\n")

        # ============ 5. COMPARABILE FINALE ============
        if analiza.comparabile:
            print(f"🏘️  COMPARABILE FOLOSITE ÎN ANALIZĂ:")
            for i, comp in enumerate(analiza.comparabile[:3], 1):
                price_str = f"€{comp.pret_eur:,.0f}" if comp.pret_eur else "N/A"
                euro_mp = f"€{comp.euro_mp:,.0f}/mp" if comp.euro_mp else "N/A"
                print(f"   {i}. {comp.sursa:15} | {price_str:12} | {comp.supr_totala:5.0f}m² | {euro_mp}")

        print(f"\n{'='*70}\n")

        # ============ 6. GENERARE PDF ============
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        pdf_path = output_dir / f"analiza_viztei_{subiect.pret_eur:.0f}eur.pdf"

        print(f"📄 Se generează PDF...\n")
        scrie_pdf(
            analiza,
            str(pdf_path),
            narativ={
                "tinta_zile": tinta_zile,
                "strategy": f"Vânzare țintă în {tinta_zile} zile"
            }
        )
        print(f"✅ PDF generat: {pdf_path}\n")
        print(f"📊 Raport complet disponibil la: {pdf_path.absolute()}\n")

    except Exception as e:
        print(f"❌ EROARE: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys

    # Acceptă opțional tinta_zile ca argument CLI
    tinta_zile = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    print(f"\n⏱️  Țintă vânzare: {tinta_zile} zile\n")
    test_live_subject(tinta_zile=tinta_zile)
