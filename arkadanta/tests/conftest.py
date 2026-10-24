"""Tes backend selalu memakai penyimpanan sementara, bukan dataset penelitian."""
import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_backend_storage(tmp_path, monkeypatch):
    drop_zone = tmp_path / "drop_zone"
    models = tmp_path / "models"
    drop_zone.mkdir()
    models.mkdir()
    for name in (
        "backend.config", "data.storage", "backend.scheduler",
        "backend.ingestion.dynamic_pipeline", "backend.api.ingestion_routes",
        "backend.api.analytics_routes", "backend.ml.model_trainer", "backend.ml.model_predictor",
    ):
        module = importlib.import_module(name)
        if hasattr(module, "DROP_ZONE_DIR"):
            monkeypatch.setattr(module, "DROP_ZONE_DIR", drop_zone)
        if hasattr(module, "MODELS_DIR"):
            monkeypatch.setattr(module, "MODELS_DIR", models)
        if hasattr(module, "AUDIT_LOG_PATH"):
            monkeypatch.setattr(module, "AUDIT_LOG_PATH", tmp_path / "audit.json")
    monkeypatch.delenv("ARKADANTA_ENABLE_HDFS", raising=False)
