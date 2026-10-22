import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))

from parser import parse_file


@pytest.mark.parametrize("filename", ["sample.csv", "sample.json"])
def test_parse_supported_file(filename):
    file_path = BASE_DIR / "data" / "raw" / filename
    df = parse_file(file_path)

    assert df.shape == (5, 8)
    assert list(df.columns) == [
        "timestamp", "open", "high", "low",
        "close", "volume", "asset", "interval"
    ]
