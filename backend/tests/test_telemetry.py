"""Telemetrie AI per dosar: apeluri Bedrock, tokeni, cache hits, cost și blocul `ai` din /api/metrics."""
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.contracts import LlmUsage
from app.core import llm, telemetry
from app.main import app

client = TestClient(app)


class FakeBedrock:
    """Răspunde ca Converse API: JSON gol (agenții merg pe fallback) + usage cu tokeni."""

    def __init__(self):
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        return {"output": {"message": {"content": [{"text": "{}"}]}},
                "usage": {"inputTokens": 1000, "outputTokens": 200}}


@pytest.fixture
def fake_bedrock(monkeypatch, tmp_path):
    fake = FakeBedrock()
    monkeypatch.setattr(config, "llm_enabled", lambda: True)
    monkeypatch.setattr(config, "LLM_MODEL", "us.amazon.nova-pro-v1:0")
    monkeypatch.setattr(llm, "_CACHE_DIR", tmp_path / "llm_cache")
    monkeypatch.setattr(llm, "_get_bedrock_client", lambda: fake)
    return fake


def test_cost_uses_model_price_table():
    # Nova Pro: 0.0008 $/1K input, 0.0032 $/1K output
    assert telemetry.cost_usd("us.amazon.nova-pro-v1:0", 1000, 200) == pytest.approx(0.00144)
    assert telemetry.price_for("anthropic.claude-3-5-sonnet-20241022-v2:0") == (0.003, 0.015)
    assert telemetry.price_for("model-necunoscut") == telemetry.PRICING_USD_PER_1K["amazon.nova-pro"]


def test_calls_outside_a_case_are_not_counted(fake_bedrock):
    usage = LlmUsage()
    llm.chat_json("sistem", "fără dosar")
    with telemetry.track(usage):
        llm.chat_json("sistem", "în dosar")
    assert usage.calls == 1 and fake_bedrock.calls == 2


def test_case_counts_bedrock_calls_tokens_cost_and_cache_hits(fake_bedrock):
    """Un document atipic trece prin router-ul LLM; al doilea identic e servit din cache (cost 0)."""
    text = "Către Raiffeisen Bank\nInvitație la conferința anuală a asociației băncilor din 12.11.2026."
    first = client.post("/api/cases/upload", files={"file": ("a.txt", text.encode("utf-8"), "text/plain")},
                        data={"scenario_id": "S1"}).json()
    u = first["llm_usage"]
    assert u["calls"] == fake_bedrock.calls >= 1
    assert u["input_tokens"] == 1000 * u["calls"] and u["output_tokens"] == 200 * u["calls"]
    assert u["cost_usd"] == pytest.approx(0.00144 * u["calls"])
    assert u["cost_eur"] == pytest.approx(u["cost_usd"] * config.USD_EUR_RATE, abs=1e-6)
    assert u["models"] == ["us.amazon.nova-pro-v1:0"]

    second = client.post("/api/cases/upload", files={"file": ("b.txt", text.encode("utf-8"), "text/plain")},
                         data={"scenario_id": "S1"}).json()
    assert second["llm_usage"]["calls"] == 0 and second["llm_usage"]["cost_usd"] == 0
    assert second["llm_usage"]["cache_hits"] == u["calls"]
    assert second["llm_usage"]["cache_savings_usd"] == pytest.approx(u["cost_usd"])


def test_langgraph_agents_report_into_the_case(fake_bedrock):
    """Apelurile făcute din nodurile LangGraph (extracție, clasificare) ajung în dosarul corect."""
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    assert case["llm_usage"]["calls"] == fake_bedrock.calls >= 1


def test_hitl_rerun_adds_to_the_same_case(fake_bedrock):
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S4"}).json()
    before = case["llm_usage"]
    review = {"reviewer": "ofiter@test.ro", "overrides": [{"tx_id": "TX-S4-10", "category": "SALARIU"}],
              "resolve_codes": ["E06"]}
    after = client.post(f"/api/cases/{case['case_id']}/review", json=review).json()["llm_usage"]
    assert after["calls"] + after["cache_hits"] > before["calls"] + before["cache_hits"]
    assert after["cost_usd"] >= before["cost_usd"]


def test_failed_bedrock_call_is_counted(monkeypatch, tmp_path):
    class Broken:
        def converse(self, **kwargs):
            raise RuntimeError("timeout")
    monkeypatch.setattr(config, "llm_enabled", lambda: True)
    monkeypatch.setattr(llm, "_CACHE_DIR", tmp_path / "llm_cache")
    monkeypatch.setattr(llm, "_get_bedrock_client", lambda: Broken())
    usage = LlmUsage()
    with telemetry.track(usage):
        assert llm.chat_json("sistem", "x") is None
    assert usage.failed_calls == 1 and usage.calls == 0 and usage.cost_usd == 0


def test_metrics_expose_ai_cost_and_roi(fake_bedrock, monkeypatch):
    monkeypatch.setattr(main, "CASES", {})
    client.post("/api/cases/from-scenario", json={"scenario_id": "S1"})   # AUTO_PROCESSED
    client.post("/api/cases/from-scenario", json={"scenario_id": "S4"})   # trimis la ofițer
    ai = client.get("/api/metrics").json()["ai"]
    assert ai["llm_calls"] == fake_bedrock.calls
    assert ai["total_cost_usd"] > 0
    assert ai["avg_cost_per_case_usd"] == pytest.approx(ai["total_cost_usd"] / 2, abs=1e-6)
    # 15 min x 15 EUR/h = 3.75 EUR economisiți doar pentru dosarul închis automat
    assert ai["automated_cases"] == 1
    assert ai["manual_cost_per_case_eur"] == pytest.approx(
        config.OFFICER_MINUTES_PER_CASE / 60 * config.OFFICER_HOURLY_COST_EUR)
    assert ai["officer_hours_saved"] == pytest.approx(config.OFFICER_MINUTES_PER_CASE / 60)
    assert ai["net_savings_eur"] == pytest.approx(ai["manual_cost_avoided_eur"] - ai["total_cost_eur"], abs=0.01)
    assert ai["roi_multiple"] > 100
    assert "amazon.nova-pro" in ai["pricing"]


def test_metrics_without_llm_have_zero_cost_and_no_roi_multiple(monkeypatch):
    monkeypatch.setattr(main, "CASES", {})
    monkeypatch.setattr(config, "llm_enabled", lambda: False)
    client.post("/api/cases/from-scenario", json={"scenario_id": "S1"})
    ai = client.get("/api/metrics").json()["ai"]
    assert ai["llm_calls"] == 0 and ai["total_cost_usd"] == 0
    assert ai["roi_multiple"] is None and ai["manual_cost_avoided_eur"] > 0
