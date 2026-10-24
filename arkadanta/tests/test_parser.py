import sys
from pathlib import Path

try:
    import pytest
    parametrize = pytest.mark.parametrize
except ImportError:
    def parametrize(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))

from parser import parse_file


@parametrize("filename", ["sample.csv", "sample.json"])
def test_parse_supported_file(filename):
    file_path = BASE_DIR / "data" / "raw" / filename
    df = parse_file(file_path)

    assert df.shape == (5, 8)
    assert list(df.columns) == [
        "timestamp", "open", "high", "low",
        "close", "volume", "asset", "interval"
    ]
