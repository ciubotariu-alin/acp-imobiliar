from io import BytesIO

from PIL import Image

from acp.poze_fetch import hashuri_din_urls, construieste_fetch_poze
from acp.imagini import dhash
from acp.modele import Comparabila


def _png_bytes(fx=70, fy=15, size=64):
    img = Image.new("L", (size, size))
    img.putdata([((x // 8) * fx + (y // 8) * fy) % 256
                 for y in range(size) for x in range(size)])
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_hashuri_din_urls_calculeaza_dhash():
    octeti = _png_bytes()

    def _descarca(url, user_agent, timeout=10.0):
        return octeti

    out = hashuri_din_urls(["https://x.ro/a.jpg"], "UA", descarca=_descarca)
    assert out == [dhash(octeti)]


def test_hashuri_din_urls_sare_descarcarile_esuate():
    def _descarca(url, user_agent, timeout=10.0):
        return None

    out = hashuri_din_urls(["https://x.ro/a.jpg", "https://x.ro/b.jpg"], "UA", descarca=_descarca)
    assert out == []


def test_hashuri_din_urls_cap_la_max():
    octeti = _png_bytes()
    apeluri = []

    def _descarca(url, user_agent, timeout=10.0):
        apeluri.append(url)
        return octeti

    urls = [f"https://x.ro/{i}.jpg" for i in range(10)]
    hashuri_din_urls(urls, "UA", descarca=_descarca, max_poze=3)
    assert len(apeluri) == 3


def test_fetch_poze_foloseste_poze_urls_si_cache():
    octeti = _png_bytes()
    c = Comparabila(sursa="s", supr_totala=60, url="https://x.ro/anunt",
                    poze_urls=["https://x.ro/a.jpg"])
    apeluri = []

    def _descarca(url, user_agent, timeout=10.0):
        apeluri.append(url)
        return octeti

    class _Cache:
        def __init__(self):
            self.store = {}
        def get(self, url):
            return self.store.get(url)
        def set(self, url, hashuri):
            self.store[url] = hashuri

    cache = _Cache()
    fetch = construieste_fetch_poze("UA", cache=cache, descarca=_descarca)
    out1 = fetch(c)
    out2 = fetch(c)  # a doua oară din cache
    assert out1 == [dhash(octeti)]
    assert out2 == out1
    assert len(apeluri) == 1  # descărcat o singură dată (cache hit la al doilea apel)
