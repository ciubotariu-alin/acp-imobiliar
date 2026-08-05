"""Motor pur de deduplicare pe poze + excludere subiect.

Metadata = pre-filtru ieftin (marchează perechi suspecte). Pozele = verdictul:
`fetch_poze` (injectabil, fără rețea în teste) întoarce hash-urile de poze ale
unei comparabile; confirmăm duplicatul dacă o pereche de poze e sub pragul Hamming.
"""
from __future__ import annotations

from typing import Callable

from acp.imagini import distanta_hamming
from acp.modele import Comparabila, Subiect


def sunt_candidat_duplicat(a: Comparabila, b: Comparabila,
                           prag_supr: float = 2.0, prag_pret_pct: float = 0.01) -> bool:
    """Pre-filtru metadata: același etaj, aceleași camere (dacă ambele știute),
    suprafață în ±prag_supr mp, preț în ±prag_pret_pct."""
    if a.etaj != b.etaj:
        return False
    if a.camere is not None and b.camere is not None and a.camere != b.camere:
        return False
    if abs(a.supr_totala - b.supr_totala) > prag_supr:
        return False
    if a.pret_eur is None or b.pret_eur is None:
        return False
    if abs(a.pret_eur - b.pret_eur) > prag_pret_pct * max(a.pret_eur, b.pret_eur):
        return False
    return True


def potrivire_metadata_subiect(subiect: Subiect, c: Comparabila,
                               prag_supr: float = 2.0, prag_pret_pct: float = 0.01) -> bool:
    """Pre-filtru: comparabila `c` se potrivește cu subiectul (etaj, camere, supr, preț)."""
    if subiect.etaj != c.etaj:
        return False
    if c.camere is not None and subiect.camere != c.camere:
        return False
    if abs(subiect.supr_totala - c.supr_totala) > prag_supr:
        return False
    if c.pret_eur is None:
        return False
    if abs(subiect.pret_eur - c.pret_eur) > prag_pret_pct * max(subiect.pret_eur, c.pret_eur):
        return False
    return True


def _poze_se_potrivesc(hashes_a: list[int], hashes_b: list[int], prag_hamming: int) -> bool:
    """True dacă vreo pereche de hash-uri e sub pragul Hamming (aceeași poză)."""
    for ha in hashes_a:
        for hb in hashes_b:
            if distanta_hamming(ha, hb) <= prag_hamming:
                return True
    return False


def confirma_si_dedup(
    comparabile: list[Comparabila],
    subiect: Subiect,
    subiect_hashes: list[int],
    fetch_poze: Callable[[Comparabila], list[int]],
    prag_hamming: int = 8,
) -> tuple[list[Comparabila], list[Comparabila], list[Comparabila]]:
    """Întoarce (pastrate, duplicate_eliminate, subiect_eliminate).

    - Descarcă hash-uri (via `fetch_poze`) DOAR pentru comparabilele candidate
      (față de subiect sau față de altă comparabilă). Restul rămân neatinse.
    - Comparabilă care se potrivește pe metadata cu subiectul ȘI împarte o poză
      cu `subiect_hashes` → subiect_eliminate. Fără `subiect_hashes` → excludere
      doar pe metadata (fallback), fără descărcare de poze.
    - Două candidate care împart o poză → același apartament; se păstrează prima
      văzută, cealaltă în duplicate_eliminate.
    """
    hashes_cache: dict[int, list[int]] = {}

    def hashes_pentru(c: Comparabila) -> list[int]:
        if id(c) not in hashes_cache:
            hashes_cache[id(c)] = fetch_poze(c)
        return hashes_cache[id(c)]

    # --- Pas 1: excludere subiect ---
    subiect_eliminate: list[Comparabila] = []
    ramase: list[Comparabila] = []
    for c in comparabile:
        if not potrivire_metadata_subiect(subiect, c):
            ramase.append(c)
            continue
        if not subiect_hashes:
            # Fallback: fără poze de subiect, excludem pe metadata (risc mic).
            subiect_eliminate.append(c)
            continue
        if _poze_se_potrivesc(hashes_pentru(c), subiect_hashes, prag_hamming):
            subiect_eliminate.append(c)
        else:
            ramase.append(c)

    # --- Pas 2: dedup cross-agenție între comparabilele rămase ---
    pastrate: list[Comparabila] = []
    duplicate_eliminate: list[Comparabila] = []
    for c in ramase:
        gasit_duplicat = False
        for pastrat in pastrate:
            if sunt_candidat_duplicat(c, pastrat) and _poze_se_potrivesc(
                hashes_pentru(c), hashes_pentru(pastrat), prag_hamming
            ):
                gasit_duplicat = True
                break
        if gasit_duplicat:
            duplicate_eliminate.append(c)
        else:
            pastrate.append(c)

    return pastrate, duplicate_eliminate, subiect_eliminate
