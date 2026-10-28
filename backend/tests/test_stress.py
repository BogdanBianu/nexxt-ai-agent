"""Teste de stres: încearcă să strice platforma cu documente și cereri ostile. Proprietar: Om2.

Două tipuri de teste:
- normale: probleme găsite și reparate (trebuie să treacă mereu);
- `xfail(strict=True)`: BUG-uri cunoscute, încă nereparate, în fișierele altui membru. Suita rămâne verde,
  dar când bug-ul e reparat testul devine roșu („XPASS strict”) — atunci ștergeți marcajul `xfail`.
"""
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.contracts import Scenario
from app.main import app

client = TestClient(app)
S1_TEXT_CNP = "IONESCU MIHAI, CNP: 1850615400011"


def known_bug(owner: str, reason: str):
    return pytest.mark.xfail(strict=True, reason=f"BUG cunoscut ({owner}): {reason}")


def run_variant(monkeypatch, base="S1", text=None, bank=None, review=None) -> dict:
    """Rulează o variantă a unui scenariu existent (text sau bancă modificate) prin API."""
    raw = json.loads((config.SCENARIOS_DIR / f"{base}.json").read_text(encoding="utf-8"))
    if text:
        raw["document"]["text"] = text(raw["document"]["text"])
    if bank:
        bank(raw["bank"])
    variant = Scenario.model_validate(raw)
    monkeypatch.setattr(main, "load_scenario", lambda sid: variant)
    case = client.post("/api/cases/from-scenario", json={"scenario_id": base}).json()
    if review:
        case = client.post(f"/api/cases/{case['case_id']}/review", json=review).json()
    return case


def codes(case) -> list[str]:
    return sorted({e["code"] for e in case["exceptions"] if not e["resolved"]})


def hold(case) -> Decimal:
    return Decimal(str((case["decision"] or {}).get("amount_to_hold", 0)))


# ---------- API: cereri ostile (reparate) ----------

def test_path_traversal_in_scenario_id_is_404_not_500():
    for bad in ["../payers_registry", "..\\payers_registry", "S1/../../S1", "", "S1.json"]:
        res = client.post("/api/cases/from-scenario", json={"scenario_id": bad})
        assert res.status_code == 404, bad
        assert str(config.DATA_DIR) not in res.json()["detail"]      # fără căi de pe server în mesaj


def test_corrupt_pdf_is_rejected_cleanly():
    res = client.post("/api/cases/upload", files={"file": ("x.pdf", b"%PDF-1.4 garbage \x00\xff", "application/pdf")})
    assert res.status_code == 422


def test_binary_garbage_txt_does_not_crash():
    res = client.post("/api/cases/upload", files={"file": ("a.txt", b"\xff\xfe\x00\x00garbage", "text/plain")})
    assert res.status_code == 200
    assert res.json()["status"] != "FAILED"


def test_review_with_unknown_tx_and_on_other_module_does_not_crash():
    s1 = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    res = client.post(f"/api/cases/{s1['case_id']}/review",
                      json={"reviewer": "x", "overrides": [{"tx_id": "NU-EXISTA", "category": "SALARIU"}]})
    assert res.status_code == 200 and res.json()["status"] != "FAILED"

    s8 = client.post("/api/cases/from-scenario", json={"scenario_id": "S8"}).json()
    res = client.post(f"/api/cases/{s8['case_id']}/review", json={"reviewer": "x", "resolve_codes": ["E01"]})
    assert res.status_code == 200 and res.json()["status"] != "FAILED"
    assert res.json()["module_id"] == "autoritati"


def test_invalid_review_payload_is_422():
    s1 = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    res = client.post(f"/api/cases/{s1['case_id']}/review",
                      json={"reviewer": "x", "overrides": [{"tx_id": "TX-1001", "category": "BITCOIN"}]})
    assert res.status_code == 422


@pytest.mark.parametrize("method,path", [
    ("get", "/api/cases/NU"), ("get", "/api/cases/NU/audit"), ("get", "/api/cases/NU/response-pdf"),
])
def test_unknown_case_is_404(method, path):
    assert getattr(client, method)(path).status_code == 404


def test_metrics_survive_mixed_and_failed_cases():
    for sid in ["S1", "S4", "S8"]:
        client.post("/api/cases/from-scenario", json={"scenario_id": sid})
    client.post("/api/cases/upload", files={"file": ("a.txt", b"\xff\xfe garbage", "text/plain")})
    m = client.get("/api/metrics").json()
    assert m["total_cases"] == 4 and 0 <= m["automation_rate"] <= 100


# ---------- bani: probleme găsite și reparate ----------

def test_same_address_twice_is_duplicate_not_double_hold():
    """Fără registru, a doua trimitere a aceleiași adrese bloca încă 5.800 RON (11.600 în total)."""
    first = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    second = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    assert first["status"] == "AUTO_PROCESSED" and hold(first) == Decimal("5800")
    assert second["status"] == "EXCEPTION_FLAGGED" and codes(second) == ["E02"]
    assert hold(second) == 0


def test_hitl_rerun_does_not_flag_its_own_case_as_duplicate():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    again = client.post(f"/api/cases/{case['case_id']}/review", json={"reviewer": "x"}).json()
    assert again["status"] == "AUTO_PROCESSED" and codes(again) == []


def test_sistare_frees_the_case_number(monkeypatch):
    client.post("/api/cases/from-scenario", json={"scenario_id": "S1"})
    sistare = run_variant(monkeypatch, text=lambda t: t.replace("ÎNFIINȚARE A POPRIRII", "SISTARE A POPRIRII")
                          .replace("ÎNFIINȚAREA POPRIRII", "SISTAREA POPRIRII"))
    assert sistare["status"] == "LIFTED"
    monkeypatch.undo()
    again = client.post("/api/cases/from-scenario", json={"scenario_id": "S1"}).json()
    assert again["status"] == "AUTO_PROCESSED"


def test_scenarios_are_separate_banks():
    """S1 și S4 au același CNP, dar sunt bănci (scenarii) diferite: nu se văd ca duplicat una pe alta."""
    client.post("/api/cases/from-scenario", json={"scenario_id": "S1"})
    s4 = client.post("/api/cases/from-scenario", json={"scenario_id": "S4"}).json()
    assert codes(s4) == ["E06"]


def test_eur_opening_balance_is_converted_before_seizing(monkeypatch):
    """Un sold de 1.000 EUR era luat drept 1.000 RON (se bloca 6.800 în loc de 10.775)."""
    def add_eur(bank):
        bank["accounts"].append({"iban": "RO09BCYP0000001234567890", "customer_id": "CUST-001",
                                 "account_type": "ECONOMII", "currency": "EUR",
                                 "opening_balance": 1000.0, "current_balance": 1000.0})
    case = run_variant(monkeypatch, bank=add_eur)
    assert hold(case) == Decimal("10775")      # 5.800 + 1.000 EUR × 4,9750


def test_hold_never_exceeds_money_in_the_account(monkeypatch):
    """Încasările au fost cheltuite: în cont mai sunt 100 RON. Nu se pot bloca 5.800 RON."""
    def drained(bank):
        bank["accounts"][0]["current_balance"] = 100.0
    case = run_variant(monkeypatch, bank=drained)
    assert hold(case) == Decimal("100")
    assert "R-BAL-11" in [r["rule_id"] for r in case["decision"]["rules_applied"]]


def test_negative_balance_holds_nothing(monkeypatch):
    def overdraft(bank):
        bank["accounts"][0]["current_balance"] = -250.0
    assert hold(run_variant(monkeypatch, bank=overdraft)) == 0


# ---------- BUG-uri cunoscute, încă nereparate (Om1) ----------

@known_bug("Om1, agents/outcome.py", "dacă ofițerul rezolvă E01, decision e None și outcome crapă (AttributeError)")
def test_resolving_identity_exception_does_not_crash(monkeypatch):
    case = run_variant(monkeypatch, text=lambda t: t.replace("1850615400011", "1850615400019"),
                       review={"reviewer": "x", "resolve_codes": ["E01"]})
    assert case["status"] != "FAILED"


@known_bug("Om1, agents/outcome.py", "rezolvarea duplicatului E02 (S6) crapă la fel")
def test_resolving_duplicate_does_not_crash():
    s6 = client.post("/api/cases/from-scenario", json={"scenario_id": "S6"}).json()
    res = client.post(f"/api/cases/{s6['case_id']}/review", json={"reviewer": "x", "resolve_codes": ["E02"]}).json()
    assert res["status"] != "FAILED"


@known_bug("Om1, agents/outcome.py",
           "fără cont CURENT nu se emite niciun ordin de blocare, dar dosarul apare AUTO_PROCESSED cu 5.800 RON blocați")
def test_hold_instruction_exists_when_client_has_only_savings_account(monkeypatch):
    def savings_only(bank):
        bank["accounts"][0]["account_type"] = "ECONOMII"
    case = run_variant(monkeypatch, bank=savings_only)
    assert case["status"] == "AUTO_PROCESSED"
    assert sum(h["amount"] for h in case["decision"]["hold_instructions"]) == float(hold(case))


@known_bug("Om1, agents/income_classifier.py",
           "formele articulate („Alocatia”, „Salariul”, „Pensia”) nu sunt recunoscute: alocația copilului de la un "
           "plătitor necunoscut devine ALT_VENIT și e poprită 100%, fără alertă (sub pragul E03 de 500 RON)")
def test_child_allowance_with_articulated_word_is_protected(monkeypatch):
    def unknown_payer(bank):
        for t in bank["transactions"]:
            if "Alocatie" in t["description"]:
                t.update(description="Alocatia lunara copil", counterparty_name="FUNDATIA SPERANTA",
                         counterparty_iban=None)
    case = run_variant(monkeypatch, bank=unknown_payer)
    assert hold(case) == Decimal("5800")       # alocația rămâne protejată


@known_bug("Om1, agents/extraction.py", "data emiterii în viitor nu e verificată (validate_issue_date nefolosit)")
def test_issue_date_in_the_future_is_flagged(monkeypatch):
    case = run_variant(monkeypatch, text=lambda t: t.replace("Data: 25.10.2026", "Data: 25.12.2027"))
    assert case["status"] == "EXCEPTION_FLAGGED" and "E05" in codes(case)


@known_bug("Om1, agents/extraction.py", "sumele fără zecimale („15000 RON”) nu sunt citite -> E05 pe o adresă validă")
def test_amounts_without_decimals_are_read(monkeypatch):
    case = run_variant(monkeypatch, text=lambda t: t.replace("14.000,00", "14000").replace("1.000,00", "1000")
                       .replace("15.000,00", "15000"))
    assert case["status"] == "AUTO_PROCESSED" and hold(case) == Decimal("5800")


@known_bug("Om1, agents/extraction.py", "CUI cu prefix „RO” (firme plătitoare de TVA) nu e extras -> E05 + E01")
def test_company_cui_with_ro_prefix_is_extracted(monkeypatch):
    def company(bank):
        bank["customers"][0].update(full_name="TECH SOLUTIONS SRL", national_id="18547290", is_legal_entity=True)
    case = run_variant(monkeypatch, bank=company,
                       text=lambda t: t.replace(S1_TEXT_CNP, "TECH SOLUTIONS SRL, CUI: RO18547290"))
    assert case["order"]["debtor_id"] == "18547290"
    assert "E01" not in codes(case) and "E05" not in codes(case)


@known_bug("Om1, agents/extraction.py",
           "la sistare, total_due lipsă e iertat în `missing`, dar nu și în `low` -> orice sistare fără sumă ia E05")
def test_sistare_without_amount_is_not_invalid(monkeypatch):
    case = run_variant(monkeypatch, base="S7", text=lambda t: "\n".join(
        line for line in t.splitlines() if not line.startswith("Total de recuperat")))
    assert case["status"] == "LIFTED" and codes(case) == []
