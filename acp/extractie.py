"""Extractori keyword pe textul brut al anunțului (titlu + descriere + tag-uri).

Conservator prin design: ambiguu → None (sau încredere joasă pentru stare).
Nu fabricăm valoare din limbaj de marketing.
"""
from __future__ import annotations

import re

_STRUCTURA = [
    ("caramida", ["caramida", "cărămidă"]),
    ("panou", ["panou", "prefabricat", "prefab"]),
    ("bca", ["bca"]),
    ("beton", ["beton", "cadre"]),
]

_INCALZIRE = [
    ("centrala_proprie", ["centrala proprie", "centrală proprie",
                          "centrala termica proprie", "centrală termică proprie"]),
    ("centrala_bloc", ["centrala de bloc", "centrală de bloc", "centrala bloc"]),
    ("termoficare", ["termoficare", "racord termic", "sistem centralizat"]),
]

_STARE_NECESITA = ["necesita renovare", "necesită renovare", "de renovat", "pentru renovare"]
_STARE_RENOVAT = ["renovat", "modernizat", "renovare recenta", "renovare recentă"]
_STARE_MARKETING = ["lux", "premium", "finisaje de calitate"]
_STARE_GRI = ["la gri", "semifinisat", "nefinisat", "la rosu", "la roșu"]

_PARCARE_LIPSA = ["fără nicio mențiune de parcare", "fără parcare"]
_PARCARE_RESEDINTA = ["loc de resedinta", "loc de reședință", "parcare adp",
                      "inchiriat de la primarie", "închiriat de la primărie"]
_PARCARE_OWNED = ["garaj", "subteran", "parcare proprie", "loc cu act",
                  "parcare inclusa", "parcare inclusă"]
_PARCARE_ORICE = ["parcare", "loc de parcare"]


def _contine(text: str, kws: list[str]) -> bool:
    return any(k in text for k in kws)


def extrage_structura(text: str) -> str | None:
    t = text.lower()
    for eticheta, kws in _STRUCTURA:
        if _contine(t, kws):
            return eticheta
    return None


def extrage_incalzire(text: str) -> str | None:
    t = text.lower()
    for eticheta, kws in _INCALZIRE:
        if _contine(t, kws):
            return eticheta
    return None


def extrage_stare(text: str) -> tuple[str | None, float]:
    t = text.lower()
    if _contine(t, _STARE_NECESITA):
        return "necesita_renovare", 0.8
    if _contine(t, _STARE_GRI):
        return "gri", 0.8
    if _contine(t, _STARE_RENOVAT):
        return "renovat", 0.7
    if _contine(t, _STARE_MARKETING):
        return "renovat", 0.4  # marketing → sub prag, nu ajustează
    return None, 0.0


def extrage_parcare(text: str, an: int | None = None) -> str | None:
    t = text.lower()
    if _contine(t, _PARCARE_RESEDINTA):
        return "resedinta"
    if _contine(t, _PARCARE_OWNED):
        return "owned"
    if _contine(t, _PARCARE_LIPSA):
        return "none"
    if _contine(t, _PARCARE_ORICE):
        if an is not None and an >= 2008:
            return "owned"
        if an is not None and an < 2000:
            return "resedinta"
        return None  # ambiguu, vechime neconcludentă
    return "none"


# Cuvinte-cheie de dotări — sursă unică; acp/ajustari.py le importă (evită drift).
KW_MOBILAT = ["mobilat", "utilat"]
KW_AC = ["aer conditionat", "aer condiționat", "a/c", "aer cond", "clima"]
KW_BALCON = ["balcon", "balcoane", "terasa", "terasă", "logie"]
KW_BOXA = ["boxa", "boxă", "debara", "camara", "cămară"]

_DOTARI_ETICHETE = [
    ("mobilat", KW_MOBILAT),
    ("aer condiționat", KW_AC),
    ("balcon", KW_BALCON),
    ("boxă", KW_BOXA),
]

_ETAJE_RE = re.compile(r"P\s*\+\s*(\d+)\s*E", re.IGNORECASE)


def extrage_dotari(text: str) -> list[str]:
    """Detectează dotările din text → etichete canonice care conțin cuvintele-cheie KW_*."""
    t = text.lower()
    return [eticheta for eticheta, kws in _DOTARI_ETICHETE if any(k in t for k in kws)]


def extrage_etaje_total(text: str) -> int | None:
    """Parsează regimul de înălțime „P+NE" → N (nr. etaje peste parter)."""
    m = _ETAJE_RE.search(text)
    return int(m.group(1)) if m else None
