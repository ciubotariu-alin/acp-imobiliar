# ACP Imobiliar — Analiză Comparativă de Piață

Automatism pentru generare rapoarte ACP în format PDF, cu conectori la 9 portaluri imobiliare.

## Setup

```bash
cd ~/OwnDevelopment/acp-imobiliar
uv sync --extra dev

# macOS: WeasyPrint necesită dependențe sistem
brew install pango gdk-pixbuf libffi
```

## Usage (Semi-Asistat)

1. Deschizi proiectul în Claude Code / Chat
2. Dai comanda cu link (sau date manuale) + ținta de zile
3. Agent: extrage fișă → caută pe portaluri → filtrează → arată verdict
4. Tu: confirmi / ajustezi
5. Agent: scrie narativul + generează PDF în `output/`

### Demo

```bash
cd ~/OwnDevelopment/acp-imobiliar
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run python exemple/demo.py
# → output/ACP_ConfortCity_90zile.pdf
```

## Architecture

```
[0] INPUT (agent + data manual)
  ↓
[1] FIȘA SUBIECTULUI (extract/normalize)
  ↓
[2] LOCALIZARE (zone normalization)
  ↓
[3] CONECTORI (9 portaluri paralel: 3 Playwright + 6 fetch)
  ↓
[4] FILTRARE & DEDUP (outliers, cross-portal)
  ↓
[4.5] ÎMBOGĂȚIRE CU DETALII (acp/detalii.py + acp/cache_detalii.py: structură, dotări din pagina de detaliu; cache `.cache/detalii` TTL 1 zi; toggle `imbogateste`)
  ↓
[5] ANALIZĂ (€/mp, statistici, poziționare)
  ↓
[6] NARATIV (agent: 20 de ani, strategie N zile, text anunț)
  ↓
[7] RANDARE PDF (HTML → PDF, bleumarin/crem)
```

### Proiect Structură

- `acp/modele.py` — modele de date (Property, Market, Listing)
- `acp/statistica.py`, `acp/filtrare.py`, `acp/context.py`, `acp/analiza.py` — nucleu determinist
- `acp/connectors/` — 9 conectori: 3 Playwright (imobiliare.ro, storia.ro, olx.ro) + 6 Fetch (publi24.ro, romimo.ro, sudrezidential.ro, lajumate.ro, waa2.com, anuntul.ro)
- `acp/raport/` — template HTML + randare PDF (WeasyPrint)
- `acp/core/pipeline.py` — PipelineOrchestrator: orchestrare end-to-end [0]-[7]
- `SKILL.md` — instrucțiunile agentului (persona 20 ani)

## Tests

```bash
# Full suite
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/ -v

# Specific module
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_e2e.py -v
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_pipeline.py -v
```

**Notă pe macOS:** WeasyPrint are nevoie de `DYLD_LIBRARY_PATH=/opt/homebrew/lib` la rulare (după `brew install pango gdk-pixbuf libffi`).

## Conectori Status

| Portal | Status | Type | Notes |
|--------|--------|------|-------|
| imobiliare.ro | Implemented | Playwright | Anti-bot detection |
| storia.ro | Implemented | Playwright | Anti-bot detection |
| olx.ro | Implemented | Playwright | Dynamic rendering |
| publi24.ro | Scaffold / TODO | Fetch | Parser stub |
| romimo.ro | Scaffold / TODO | Fetch | Parser stub |
| sudrezidential.ro | Scaffold / TODO | Fetch | Parser stub |
| lajumate.ro | Scaffold / TODO | Fetch | Parser stub |
| waa2.com | Scaffold / TODO | Fetch | Parser stub |
| anuntul.ro | Scaffold / TODO | Fetch | Parser stub |

## Disclaimer

Document confidențial. Estimare analitică, **nu evaluare autorizată ANEVAR**. Conform ORDIN 53/2023, rapoartele ACP generate de acest instrument sunt auxiliare și nu înlocuiesc evaluarea profesională.
