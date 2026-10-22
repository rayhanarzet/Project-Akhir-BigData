"""[ORANG 1 - KONTRAK & STUB] Deteksi format file CSV atau JSON secara otomatis."""

from typing import Literal


def detect_format(filename: str, content_sample: bytes) -> Literal["CSV", "JSON"]:
    """Mendeteksi apakah input berformat CSV atau JSON berdasarkan ekstensi dan karakter awal."""
    lower_name = filename.lower()
    stripped = content_sample.lstrip()
    if lower_name.endswith(".json") or stripped.startswith((b"{", b"[")):
        return "JSON"
    return "CSV"
