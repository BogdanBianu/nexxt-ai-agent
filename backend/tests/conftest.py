"""Pune backend/ pe sys.path, ca `pytest backend/tests` să meargă din rădăcina repo-ului."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("USE_LLM", "off")   # testele rulează mereu pe fallback-ul determinist


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Fiecare test pornește cu dosarele goale și scrie upload-uri/PDF-uri într-un folder temporar,
    nu în data/uploads și data/output ale aplicației."""
    from app import config, main
    monkeypatch.setattr(main, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    for store in (main.CASES, main.BANKS, main.EVENTS, main.PROCESSING_MS, main.AUDIT_LOG, main.REGISTERED,
                  main.INSOLVENT):
        store.clear()
    yield
