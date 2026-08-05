import acp.connectors.detaliu_fetch as df


def test_fetch_detaliu_text_intoarce_textul(monkeypatch):
    async def _fake(url, user_agent, timeout_ms):
        return "text de pe pagina de detaliu"
    monkeypatch.setattr(df, "_extrage_text_pagina", _fake)
    assert df.fetch_detaliu_text("https://x.ro/1", "UA") == "text de pe pagina de detaliu"


def test_fetch_detaliu_text_none_la_eroare(monkeypatch):
    async def _boom(url, user_agent, timeout_ms):
        raise RuntimeError("cloudflare / timeout")
    monkeypatch.setattr(df, "_extrage_text_pagina", _boom)
    assert df.fetch_detaliu_text("https://x.ro/1", "UA", retries=1) is None


def test_connector_deleaga_cu_user_agent_propriu(monkeypatch):
    from acp.connectors.imobiliare import ImobiliareConnector, USER_AGENT
    apeluri = {}

    def _fake_fetch(url, user_agent, timeout_ms=30000, retries=1):
        apeluri["url"] = url
        apeluri["ua"] = user_agent
        return "ok"
    monkeypatch.setattr(df, "fetch_detaliu_text", _fake_fetch)
    conn = ImobiliareConnector()
    assert conn.fetch_detaliu_text("https://imobiliare.ro/y") == "ok"
    assert apeluri["url"] == "https://imobiliare.ro/y"
    assert apeluri["ua"] == USER_AGENT
