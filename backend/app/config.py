"""Configurare centrală, citită din variabile de mediu / fișierul .env."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:  # python-dotenv e opțional
    pass

ROOT_DIR = Path(__file__).resolve().parents[2]          # .../lexops
DATA_DIR = ROOT_DIR / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"
OUTPUT_DIR = DATA_DIR / "output"

FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "40"))

# "auto" = folosește LLM dacă există cheie; "off" = doar reguli deterministe (demo offline)
USE_LLM = os.getenv("USE_LLM", "auto").lower()

# Pragurile de încredere (Om1 + Om2 le pot ajusta)
MIN_FIELD_CONFIDENCE = float(os.getenv("MIN_FIELD_CONFIDENCE", "0.85"))
MIN_CLASSIFICATION_CONFIDENCE = float(os.getenv("MIN_CLASSIFICATION_CONFIDENCE", "0.80"))
AMBIGUOUS_AMOUNT_THRESHOLD = float(os.getenv("AMBIGUOUS_AMOUNT_THRESHOLD", "500"))

# Fereastra de analiză a încasărilor (zile înainte de primirea adresei)
ANALYSIS_WINDOW_DAYS = int(os.getenv("ANALYSIS_WINDOW_DAYS", "30"))

RULES_FILE = os.getenv("RULES_FILE", str(ROOT_DIR / "backend/app/modules/popriri/rules/v2026_10.yaml"))


def llm_enabled() -> bool:
    if USE_LLM == "off":
        return False
    return bool(FEATHERLESS_API_KEY)
