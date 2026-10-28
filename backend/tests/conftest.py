"""Pune backend/ pe sys.path, ca `pytest backend/tests` să meargă din rădăcina repo-ului."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("USE_LLM", "off")   # testele rulează mereu pe fallback-ul determinist
