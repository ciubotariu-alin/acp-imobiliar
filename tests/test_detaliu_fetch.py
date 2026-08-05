import acp.connectors.detaliu_fetch as df


def test_extrage_poze_filtreaza_thumb_si_non_http():
    srcs = [
        "https://cdn.x.ro/gallery-thumb-1.jpg",   # thumbnail -> exclus
        "https://cdn.x.ro/foto-1.jpg",
        "data:image/png;base64,AAAA",             # non-http -> exclus
        "/local/foto-2.jpg",                       # non-http -> exclus
        "https://cdn.x.ro/foto-2.jpg",
        "https://cdn.x.ro/logo.svg",               # svg -> exclus
    ]
    assert df.extrage_poze_din_srcs(srcs) == [
        "https://cdn.x.ro/foto-1.jpg",
        "https://cdn.x.ro/foto-2.jpg",
    ]


def test_extrage_poze_dedup_si_cap_la_max():
    srcs = [f"https://cdn.x.ro/f{i}.jpg" for i in range(10)] + ["https://cdn.x.ro/f0.jpg"]
    out = df.extrage_poze_din_srcs(srcs, max_poze=4)
    assert out == [f"https://cdn.x.ro/f{i}.jpg" for i in range(4)]
    assert len(out) == 4


def test_fetch_detaliu_intoarce_text_si_poze(monkeypatch):
    async def _fake(url, user_agent, timeout_ms):
        return "text de pe pagina", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "_extrage_pagina", _fake)
    text, poze = df.fetch_detaliu("https://x.ro/1", "UA")
    assert text == "text de pe pagina"
    assert poze == ["https://cdn.x.ro/foto-1.jpg"]


def test_fetch_detaliu_none_la_eroare(monkeypatch):
    async def _boom(url, user_agent, timeout_ms):
        raise RuntimeError("cloudflare / timeout")
    monkeypatch.setattr(df, "_extrage_pagina", _boom)
    assert df.fetch_detaliu("https://x.ro/1", "UA", retries=1) == (None, [])


def test_fetch_detaliu_text_wrapper_intoarce_doar_text(monkeypatch):
    async def _fake(url, user_agent, timeout_ms):
        return "doar text", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "_extrage_pagina", _fake)
    assert df.fetch_detaliu_text("https://x.ro/1", "UA") == "doar text"


def test_connector_deleaga_fetch_detaliu_cu_user_agent_propriu(monkeypatch):
    from acp.connectors.imobiliare import ImobiliareConnector, USER_AGENT
    apeluri = {}

    def _fake_fetch(url, user_agent, timeout_ms=30000, retries=1):
        apeluri["url"] = url
        apeluri["ua"] = user_agent
        return "ok", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "fetch_detaliu", _fake_fetch)
    conn = ImobiliareConnector()
    text, poze = conn.fetch_detaliu("https://imobiliare.ro/y")
    assert text == "ok"
    assert poze == ["https://cdn.x.ro/foto-1.jpg"]
    assert apeluri["url"] == "https://imobiliare.ro/y"
    assert apeluri["ua"] == USER_AGENT
