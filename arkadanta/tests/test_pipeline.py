import sys
from pathlib import Path

import pandas as pd

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

from dynamic_pipeline import run_pipeline


@parametrize(
    "filename",
    ["sample.csv", "sample.json"],
)
def test_pipeline_processes_supported_files(filename):
    file_path = BASE_DIR / "data" / "raw" / filename

    result = run_pipeline(file_path)

    assert isinstance(result, pd.DataFrame)
    assert result.shape == (5, 8)
    assert list(result.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "asset",
        "interval",
    ]
