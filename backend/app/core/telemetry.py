"""Telemetrie AI per dosar: apeluri Bedrock, tokeni, cache hits, latență și cost estimat. Proprietar: Om2.

`_run_pipeline` deschide `track(usage)` pentru dosarul curent; clientul LLM (`llm.py`) raportează aici fiecare
apel. ContextVar-ul ține contorul separat pe cerere HTTP, iar LangGraph copiază contextul în nodurile lui,
deci apelurile făcute de orice agent ajung în dosarul corect.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from app import config
from app.contracts import LlmUsage

# Prețuri AWS Bedrock on-demand, USD per 1.000 tokeni (input, output) — lista publică, de reverificat la demo.
# Cheia se caută în ID-ul modelului (fără prefixul de regiune „us.”).
PRICING_USD_PER_1K: dict[str, tuple[float, float]] = {
    "amazon.nova-pro": (0.0008, 0.0032),
    "amazon.nova-lite": (0.00006, 0.00024),
    "amazon.nova-micro": (0.000035, 0.00014),
    "anthropic.claude-3-5-sonnet": (0.003, 0.015),
    "anthropic.claude-3-5-haiku": (0.0008, 0.004),
    "anthropic.claude-3-haiku": (0.00025, 0.00125),
}
_DEFAULT_PRICE = PRICING_USD_PER_1K["amazon.nova-pro"]

_CURRENT: ContextVar[LlmUsage | None] = ContextVar("lexops_llm_usage", default=None)


def price_for(model_id: str) -> tuple[float, float]:
    return next((p for key, p in PRICING_USD_PER_1K.items() if key in model_id), _DEFAULT_PRICE)


def cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = price_for(model_id)
    return input_tokens / 1000 * p_in + output_tokens / 1000 * p_out


@contextmanager
def track(usage: LlmUsage):
    """Toate apelurile LLM din blocul `with` se adună în `usage` (inclusiv cele din nodurile LangGraph)."""
    token = _CURRENT.set(usage)
    try:
        yield usage
    finally:
        _CURRENT.reset(token)


def record_call(model_id: str, input_tokens: int, output_tokens: int, latency_ms: int, cached: bool) -> None:
    """Un răspuns primit: de la Bedrock (facturat) sau din cache-ul pe disc (gratuit, dar îl numărăm ca economie)."""
    usage = _CURRENT.get()
    if usage is None:
        return
    cost = cost_usd(model_id, input_tokens, output_tokens)
    if cached:
        usage.cache_hits += 1
        usage.cache_savings_usd = round(usage.cache_savings_usd + cost, 6)
        usage.latency_ms += latency_ms
        return
    usage.calls += 1
    usage.input_tokens += input_tokens
    usage.output_tokens += output_tokens
    usage.latency_ms += latency_ms
    usage.cost_usd = round(usage.cost_usd + cost, 6)
    usage.cost_eur = round(usage.cost_usd * config.USD_EUR_RATE, 6)
    if model_id not in usage.models:
        usage.models.append(model_id)


def record_failure() -> None:
    """Apel LLM eșuat (timeout, credențiale expirate): agentul a mers pe fallback-ul determinist."""
    usage = _CURRENT.get()
    if usage is not None:
        usage.failed_calls += 1
