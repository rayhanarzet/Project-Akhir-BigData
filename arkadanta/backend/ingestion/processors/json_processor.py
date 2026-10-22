"""[ORANG 1 - KONTRAK & STUB] Parser JSON (termasuk JSON bertingkat seperti response data/records)."""

import io
import json
import pandas as pd


def parse_json_bytes(content: bytes) -> pd.DataFrame:
    raw = json.loads(content.decode("utf-8"))
    if isinstance(raw, dict):
        for key in ("data", "records", "klines", "items", "result"):
            if key in raw and isinstance(raw[key], list):
                raw = raw[key]
                break
    return pd.DataFrame(raw)
