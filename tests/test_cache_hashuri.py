from acp.cache_hashuri import CacheHashuri


def test_set_get_roundtrip(tmp_path):
    cache = CacheHashuri(dir=str(tmp_path / "h"))
    cache.set("https://x.ro/a", [1, 2, 3])
    assert cache.get("https://x.ro/a") == [1, 2, 3]


def test_get_miss_none(tmp_path):
    cache = CacheHashuri(dir=str(tmp_path / "h"))
    assert cache.get("https://x.ro/lipsa") is None


def test_ttl_expira(tmp_path):
    cache = CacheHashuri(dir=str(tmp_path / "h"), ttl_zile=0.0)
    cache.set("https://x.ro/a", [1])
    assert cache.get("https://x.ro/a") is None
