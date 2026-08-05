from io import BytesIO

from PIL import Image

from acp.imagini import dhash, distanta_hamming


def _img_pattern(fx: int, fy: int, size: int = 64) -> Image.Image:
    """Imagine grayscale low-freq (blocuri 8px) — stabilă la redimensionare."""
    img = Image.new("L", (size, size))
    img.putdata([((x // 8) * fx + (y // 8) * fy) % 256
                 for y in range(size) for x in range(size)])
    return img


def _png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_distanta_hamming_numara_bitii():
    assert distanta_hamming(0b1010, 0b1000) == 1
    assert distanta_hamming(0, 0) == 0
    assert distanta_hamming(0xFFFFFFFFFFFFFFFF, 0) == 64


def test_dhash_are_64_biti():
    h = dhash(_png(_img_pattern(70, 15)))
    assert h is not None
    assert 0 <= h < (1 << 64)


def test_dhash_identic_distanta_zero():
    b = _png(_img_pattern(70, 15))
    assert distanta_hamming(dhash(b), dhash(b)) == 0


def test_dhash_redimensionare_ramane_apropiat():
    img = _img_pattern(70, 15, 64)
    mare = img.resize((128, 128), Image.LANCZOS)
    d = distanta_hamming(dhash(_png(img)), dhash(_png(mare)))
    assert d <= 8


def test_dhash_imagini_diferite_distanta_mare():
    a = dhash(_png(_img_pattern(70, 15)))
    b = dhash(_png(_img_pattern(15, 70)))
    assert distanta_hamming(a, b) > 8


def test_dhash_bytes_invalizi_none():
    assert dhash(b"nu sunt o imagine") is None
