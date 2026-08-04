"""Motor de ajustare a prețului comparabilelor la nivelul subiectului.

Direcția: subiect − comparabila. Comparabila inferioară → ajustare pozitivă.
"""
from __future__ import annotations

from acp.modele import Subiect, Comparabila, Ajustare
from acp.extractie import extrage_parcare

CAP_ETAJ = 0.05
CAP_VECHIME = 0.10
CAP_MARIME = 0.03
CAP_STARE = 0.15

_STRUCTURA_VAL = {"caramida": 0.02, "beton": 0.02, "bca": 0.0, "panou": -0.03}
_INCALZIRE_VAL = {"centrala_proprie": 0.03, "centrala_bloc": 0.0, "termoficare": -0.02}
_STARE_VAL = {"renovat": 0.10, "bun": 0.0, "gri": -0.05, "necesita_renovare": -0.15}

_KW_BOXA = ["boxa", "boxă", "debara", "camara", "cămară"]
_KW_MOBILAT = ["mobilat", "utilat"]
_KW_AC = ["aer conditionat", "aer condiționat", "a/c", "aer cond", "clima"]
_KW_BALCON = ["balcon", "terasa", "terasă", "logie"]


def _plafon(x: float, cap: float) -> float:
    return max(-cap, min(cap, x))


def _nivel_etaj(etaj: int | None, etaje_total: int | None) -> float | None:
    """Valoarea de nivel a etajului (curbă, nu liniar). None dacă etaj necunoscut."""
    if etaj is None:
        return None
    if etaj == 0:
        return -0.05          # parter
    if etaj == 1:
        return 0.02           # cel mai căutat
    if etaj in (2, 3):
        return 0.01
    if etaje_total is not None and etaj >= 4 and etaj == etaje_total:
        return -0.03          # ultimul etaj
    return 0.0                # intermediar (baseline)


def _ajustare_etaj(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    ns = _nivel_etaj(subiect.etaj, subiect.etaje_total)
    nc = _nivel_etaj(comp.etaj, comp.etaje_total)
    if ns is None or nc is None:
        return None
    procent = _plafon(ns - nc, CAP_ETAJ)
    if procent == 0:
        return None
    return Ajustare(factor="etaj", procent=procent,
                    motiv=f"Etaj {comp.etaj} vs subiect {subiect.etaj}")


def _ajustare_vechime(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if subiect.an is None or comp.an is None:
        return None
    procent = _plafon((subiect.an - comp.an) * 0.01, CAP_VECHIME)
    if procent == 0:
        return None
    return Ajustare(factor="vechime", procent=procent,
                    motiv=f"An {comp.an} vs subiect {subiect.an}")


def _ajustare_marime(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    procent = _plafon((comp.supr_totala - subiect.supr_totala) * 0.003, CAP_MARIME)
    if procent == 0:
        return None
    return Ajustare(factor="marime", procent=procent,
                    motiv=f"{comp.supr_totala}mp vs subiect {subiect.supr_totala}mp")


def _are(dotari: list[str], kws: list[str]) -> bool:
    return any(any(k in d.lower() for k in kws) for d in dotari)


def _numara_ac(dotari: list[str]) -> int:
    return sum(1 for d in dotari if any(k in d.lower() for k in _KW_AC))


def _ajustare_parcare(subiect: Subiect, comp: Comparabila, valoare: float) -> Ajustare | None:
    subiect_owned = extrage_parcare(subiect.parcare or "", subiect.an) == "owned"
    comp_owned = comp.parcare_tip == "owned"
    if subiect_owned and not comp_owned:
        return Ajustare(factor="parcare", valoare_abs=valoare,
                        motiv="Subiect cu parcare proprie, comparabila fără")
    if comp_owned and not subiect_owned:
        return Ajustare(factor="parcare", valoare_abs=-valoare,
                        motiv="Comparabila cu parcare proprie, subiect fără")
    return None


def _ajustare_boxa(subiect: Subiect, comp: Comparabila, valoare: float) -> Ajustare | None:
    s, c = _are(subiect.dotari, _KW_BOXA), _are(comp.dotari, _KW_BOXA)
    if s and not c:
        return Ajustare(factor="boxa", valoare_abs=valoare,
                        motiv="Subiect cu boxă, comparabila fără")
    if c and not s:
        return Ajustare(factor="boxa", valoare_abs=-valoare,
                        motiv="Comparabila cu boxă, subiect fără")
    return None


def _ajustare_mobilat(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    s, c = _are(subiect.dotari, _KW_MOBILAT), _are(comp.dotari, _KW_MOBILAT)
    if s and not c:
        return Ajustare(factor="mobilat", procent=0.04,
                        motiv="Subiect mobilat/utilat, comparabila nu")
    if c and not s:
        return Ajustare(factor="mobilat", procent=-0.04,
                        motiv="Comparabila mobilat/utilat, subiect nu")
    return None


def _ajustare_ac(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    diff = _numara_ac(subiect.dotari) - _numara_ac(comp.dotari)
    procent = _plafon(diff * 0.01, 0.03)
    if procent == 0:
        return None
    return Ajustare(factor="ac", procent=procent,
                    motiv=f"A/C: comparabila {_numara_ac(comp.dotari)} vs subiect {_numara_ac(subiect.dotari)}")


def _ajustare_balcon(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    s, c = _are(subiect.dotari, _KW_BALCON), _are(comp.dotari, _KW_BALCON)
    if s and not c:
        return Ajustare(factor="balcon", procent=0.03,
                        motiv="Subiect cu balcon, comparabila fără")
    if c and not s:
        return Ajustare(factor="balcon", procent=-0.03,
                        motiv="Comparabila cu balcon, subiect fără")
    return None


def _ajustare_din_harta(factor: str, val_s: str | None, val_c: str | None,
                        harta: dict[str, float], cap: float | None = None) -> Ajustare | None:
    if val_s is None or val_c is None:
        return None
    vs, vc = harta.get(val_s), harta.get(val_c)
    if vs is None or vc is None:
        return None
    procent = vs - vc
    if cap is not None:
        procent = _plafon(procent, cap)
    if procent == 0:
        return None
    return Ajustare(factor=factor, procent=procent, motiv=f"{val_c} vs subiect {val_s}")


def _ajustare_structura(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    return _ajustare_din_harta("structura", subiect.structura, comp.structura, _STRUCTURA_VAL)


def _ajustare_incalzire(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    return _ajustare_din_harta("incalzire", subiect.incalzire, comp.incalzire, _INCALZIRE_VAL)


def _ajustare_stare(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if comp.stare_incredere <= 0.5:
        return None
    return _ajustare_din_harta("stare", subiect.stare, comp.stare, _STARE_VAL, cap=CAP_STARE)


def calculeaza_ajustari(subiect: Subiect, comparabila: Comparabila,
                        valoare_parcare_eur: float = 8000.0,
                        valoare_boxa_eur: float = 2000.0) -> list[Ajustare]:
    candidati = [
        _ajustare_etaj(subiect, comparabila),
        _ajustare_vechime(subiect, comparabila),
        _ajustare_marime(subiect, comparabila),
        _ajustare_parcare(subiect, comparabila, valoare_parcare_eur),
        _ajustare_boxa(subiect, comparabila, valoare_boxa_eur),
        _ajustare_mobilat(subiect, comparabila),
        _ajustare_ac(subiect, comparabila),
        _ajustare_balcon(subiect, comparabila),
        _ajustare_structura(subiect, comparabila),
        _ajustare_incalzire(subiect, comparabila),
        _ajustare_stare(subiect, comparabila),
    ]
    return [a for a in candidati if a is not None]
