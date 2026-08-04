"""Construiește HTML din Analiza și îl randează în PDF."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from acp.modele import Analiza

_DIR = Path(__file__).parent


def formateaza_eur(x: float) -> str:
    return f"{int(round(x)):,} €".replace(",", ".")


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["eur"] = formateaza_eur
    return env


def construieste_html(analiza: Analiza, narativ: dict | None = None) -> str:
    template = _env().get_template("template.html")
    return template.render(analiza=analiza, subiect=analiza.subiect, narativ=narativ or {})


def scrie_pdf(analiza: Analiza, cale_pdf: str, narativ: dict | None = None) -> None:
    html = construieste_html(analiza, narativ)
    Path(cale_pdf).parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(cale_pdf)
