"""Modele de date pentru pipeline-ul ACP."""
from __future__ import annotations

from pydantic import BaseModel, computed_field


class Ajustare(BaseModel):
    factor: str
    procent: float = 0.0        # ajustare proporțională (etaj, vechime, stare...)
    valoare_abs: float = 0.0    # ajustare absolută în € (parcare, boxă)
    motiv: str


class Subiect(BaseModel):
    pret_eur: float
    supr_totala: float
    supr_utila: float | None = None
    camere: int
    camere_potential: str | None = None
    etaj: int | None = None
    etaje_total: int | None = None
    an: int | None = None
    structura: str | None = None
    incalzire: str | None = None
    stare: str | None = None
    dotari: list[str] = []
    locatie: str = ""
    zona_reala: str | None = None
    coordonate: tuple[float, float] | None = None
    parcare: str | None = None
    tip_vanzator: str | None = None
    url: str | None = None        # linkul anunțului subiect (agentul îl dă la pasul [0])

    @computed_field
    @property
    def euro_mp(self) -> float:
        return self.pret_eur / self.supr_totala


class Comparabila(BaseModel):
    sursa: str
    url: str | None = None
    camere: int | None = None     # pentru pre-filtrul de duplicat (connectorii îl populează)
    poze_urls: list[str] = []     # URL-uri de poze (galerie), populate la îmbogățire
    pret_eur: float | None = None
    supr_totala: float
    etaj: int | None = None
    an: int | None = None
    dotari: list[str] = []
    marcaj: str = "activ"  # activ | vandut | rezervat | listat
    tip: str = "vanzare"   # vanzare | chirie
    etaje_total: int | None = None
    structura: str | None = None      # caramida | bca | panou | beton
    incalzire: str | None = None      # centrala_proprie | termoficare | centrala_bloc
    stare: str | None = None          # renovat | bun | necesita_renovare | gri
    stare_incredere: float = 0.0      # 0-1; ajustarea de stare se aplică doar peste prag
    parcare_tip: str | None = None    # owned | resedinta | none
    ajustare_neta_mare: bool = False  # marcaj gardă anti-supra-ajustare (|net| > 0.15)
    detalii_complete: bool = False    # True doar după fetch+parse reușit al paginii de detaliu
    ajustari: list[Ajustare] = []

    @computed_field
    @property
    def euro_mp(self) -> float | None:
        if self.pret_eur is None:
            return None
        return self.pret_eur / self.supr_totala

    @computed_field
    @property
    def pret_ajustat(self) -> float | None:
        if self.pret_eur is None:
            return None
        procent = 1 + sum(a.procent for a in self.ajustari)
        absolut = sum(a.valoare_abs for a in self.ajustari)
        return self.pret_eur * procent + absolut

    @computed_field
    @property
    def euro_mp_ajustat(self) -> float | None:
        if self.pret_ajustat is None:
            return None
        return self.pret_ajustat / self.supr_totala


class CriteriiCautare(BaseModel):
    camere: int
    supr_min: float
    supr_max: float
    an_min: int | None = None
    an_max: int | None = None
    zona: str
    raza_km: float = 1.5
    tip: str = "vanzare"


class Statistici(BaseModel):
    n: int
    minim: float
    mediana: float
    maxim: float
    q1: float | None = None
    q3: float | None = None


class ContextPiata(BaseModel):
    nr_active: int
    days_on_market_med: float | None = None
    nr_cu_reduceri: int | None = None
    tensiune: str = "echilibrata"  # piata_cumparatorului | echilibrata | piata_vanzatorului


class Analiza(BaseModel):
    subiect: Subiect
    comparabile: list[Comparabila]
    outlieri: list[Comparabila] = []
    context: ContextPiata
    stat_brut: Statistici
    stat_ajustat: Statistici
    pozitionare_pct: float  # + peste mediană, - sub mediană
    incadrare: str          # sub piață | corect | supraevaluat
    pret_listare: tuple[float, float]
    pret_tranzactie: tuple[float, float]
    tinta_zile: int
    surse: list[str] = []
