"""Perceptual hashing (dHash) — pur, doar Pillow. Fără rețea, fără dependențe noi."""
from __future__ import annotations

from io import BytesIO

from PIL import Image


def dhash(imagine_bytes: bytes, hash_size: int = 8) -> int | None:
    """dHash pe (hash_size*hash_size) biți al unei imagini.

    Convertește la grayscale, redimensionează la (hash_size+1) x hash_size și
    compară fiecare pixel cu vecinul din dreapta (diferențe orizontale). Robust
    la redimensionare și recompresie. Întoarce None dacă bytes-ii nu sunt o imagine.
    """
    try:
        img = (
            Image.open(BytesIO(imagine_bytes))
            .convert("L")
            .resize((hash_size + 1, hash_size), Image.LANCZOS)
        )
    except Exception:
        return None
    pixels = list(img.tobytes())
    latime = hash_size + 1
    bits = 0
    for rand in range(hash_size):
        for col in range(hash_size):
            stanga = pixels[rand * latime + col]
            dreapta = pixels[rand * latime + col + 1]
            bits = (bits << 1) | (1 if stanga > dreapta else 0)
    return bits


def distanta_hamming(h1: int, h2: int) -> int:
    """Numărul de biți diferiți între două hash-uri (0 = identice)."""
    return bin(h1 ^ h2).count("1")
