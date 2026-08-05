import json
from acp.cache_detalii import CacheDetalii


def test_cache_miss_returneaza_none(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    assert c.get("https://x.ro/anunt/1") is None


def test_cache_set_apoi_get_hit(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    campuri = {"structura": "beton", "dotari": ["mobilat"]}
    c.set("https://x.ro/anunt/1", campuri)
    assert c.get("https://x.ro/anunt/1") == campuri


def test_cache_expirat_returneaza_none(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    url = "https://x.ro/anunt/1"
    c.set(url, {"structura": "beton"})
    # forțează expirarea: rescrie fetched_at la epoca 0
    p = c._cale(url)
    data = json.loads(p.read_text())
    data["fetched_at"] = 0.0
    p.write_text(json.dumps(data))
    assert c.get(url) is None


def test_cache_fisier_corupt_returneaza_none(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    url = "https://x.ro/anunt/1"
    c._cale(url).write_text("{ not json")
    assert c.get(url) is None
