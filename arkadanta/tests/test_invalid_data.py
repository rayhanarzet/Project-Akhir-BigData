import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))

from parser import parse_file
from validator import validate_data


def test_invalid_candle_is_rejected():
    df = parse_file(BASE_DIR / "data" / "raw" / "sample.csv")

    # High lebih rendah daripada low sehingga candle tidak valid.
    df.loc[0, "high"] = 90

    is_valid, messages = validate_data(df)

    assert is_valid is False
