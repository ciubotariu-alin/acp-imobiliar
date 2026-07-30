# ACP Imobiliar

Pipeline de Analiză Comparativă de Piață pentru anunțuri imobiliare (uz personal).

## Instalare
```bash
uv sync --extra dev
# macOS, pentru WeasyPrint:
brew install pango gdk-pixbuf libffi
```

## Rulează demo-ul
```bash
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run python exemple/demo.py
# → output/ACP_ConfortCity_90zile.pdf
```

## Teste
```bash
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -v
```

**Notă pe macOS:** WeasyPrint are nevoie de `DYLD_LIBRARY_PATH=/opt/homebrew/lib` la rulare (după `brew install pango gdk-pixbuf libffi`).

## Structură
- `acp/modele.py` — modele de date
- `acp/statistica.py`, `acp/filtrare.py`, `acp/context.py`, `acp/analiza.py` — nucleu determinist
- `acp/connectors/` — surse de comparabile (fixture acum; portaluri reale în Planul 2)
- `acp/raport/` — template HTML + randare PDF
- `acp/pipeline.py` — orchestrare end-to-end
- `SKILL.md` — instrucțiunile agentului (persona 20 ani)
