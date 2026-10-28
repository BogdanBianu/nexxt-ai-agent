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

# Credențiale AWS Bedrock
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "")

# Fallback opțional OpenAI-compatible (dacă este setat)
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")

LLM_MODEL = os.getenv("LLM_MODEL", "us.amazon.nova-pro-v1:0")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "40"))

# "auto" = folosește LLM dacă există cheie; "off" = doar reguli deterministe (demo offline)
USE_LLM = os.getenv("USE_LLM", "auto").lower()

# Pragurile de încredere (Om1 + Om2 le pot ajusta)
MIN_FIELD_CONFIDENCE = float(os.getenv("MIN_FIELD_CONFIDENCE", "0.85"))
MIN_CLASSIFICATION_CONFIDENCE = float(os.getenv("MIN_CLASSIFICATION_CONFIDENCE", "0.80"))
AMBIGUOUS_AMOUNT_THRESHOLD = float(os.getenv("AMBIGUOUS_AMOUNT_THRESHOLD", "500"))

# Fereastra de analiză a încasărilor (zile înainte de primirea adresei)
ANALYSIS_WINDOW_DAYS = int(os.getenv("ANALYSIS_WINDOW_DAYS", "30"))

# Telemetrie AI & ROI (presupuneri pentru dashboard-ul Executive Impact, ajustabile din .env)
USD_EUR_RATE = float(os.getenv("USD_EUR_RATE", "0.92"))
OFFICER_MINUTES_PER_CASE = float(os.getenv("OFFICER_MINUTES_PER_CASE", "15"))   # procesare manuală / dosar
OFFICER_HOURLY_COST_EUR = float(os.getenv("OFFICER_HOURLY_COST_EUR", "15"))     # cost complet ofițer / oră

RULES_FILE = os.getenv("RULES_FILE", str(ROOT_DIR / "backend/app/modules/popriri/rules/v2026_10.yaml"))


def llm_enabled() -> bool:
    if USE_LLM == "off":
        return False
    return bool(AWS_ACCESS_KEY_ID or FEATHERLESS_API_KEY)
