"""Teste pentru modulul „Insolvență și succesiuni”. Proprietar: Om2."""
import json
from decimal import Decimal
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.contracts import Scenario
from app.main import app
from app.modules.insolventa.module import Heir, parse_quota, split_estate

client = TestClient(app)


def approve(case: dict) -> dict:
    """Angajatul aprobă propunerea agentului: abia atunci poprirea / insolvența intră în registru."""
    res = client.post(f"/api/cases/{case['case_id']}/approve", json={"reviewer": "ofiter"})
    assert res.status_code == 200, res.text
    return res.json()


def scenario(sid: str, text=None, bank=None) -> dict:
    """Rulează scenariul `sid`, opțional cu documentul sau banca modificate."""
    raw = json.loads((config.SCENARIOS_DIR / f"{sid}.json").read_text(encoding="utf-8"))
    if text:
        raw["document"]["text"] = text(raw["document"]["text"])
    if bank:
        bank(raw["bank"])
    variant = Scenario.model_validate(raw)
    original = main.load_scenario
    main.load_scenario = lambda _sid: variant
    try:
        return client.post("/api/cases/from-scenario", json={"scenario_id": sid}).json()
    finally:
        main.load_scenario = original


def codes(case) -> list[str]:
    return sorted({e["code"] for e in case["exceptions"] if not e["resolved"]})


def shares(case) -> dict[str, Decimal]:
    return {r["description"].split("Moștenitor ")[1].split(" (")[0]: Decimal(str(r["seizable_amount"]))
            for r in case["decision"]["rules_applied"] if r["rule_id"] == "R-SUC-02"}


# ---------- cote și împărțire (determinist) ----------

@pytest.mark.parametrize("text,expected", [
    ("1/4", Fraction(1, 4)), ("3 / 8", Fraction(3, 8)), ("50%", Fraction(1, 2)), ("37,5%", Fraction(3, 8)),
    ("1/1", Fraction(1)), ("0/4", None), ("5/4", None), ("1/0", None), ("jumătate", None),
])
def test_parse_quota(text, expected):
    assert parse_quota(text) == expected


def _heirs(*quotas):
    return [Heir(f"H{i}", "", Fraction(q), q) for i, q in enumerate(quotas)]


@pytest.mark.parametrize("total,quotas", [
    ("12487.51", ["1/4", "3/8", "3/8"]), ("100.00", ["1/3", "1/3", "1/3"]), ("0.01", ["1/2", "1/2"]),
    ("999999.99", ["1/6", "1/6", "2/3"]), ("0", ["1/2", "1/2"]),
])
def test_split_estate_shares_add_up_exactly(total, quotas):
    heirs = split_estate(Decimal(total), _heirs(*quotas))
    assert sum(h.share for h in heirs) == Decimal(total)
    assert all(h.share >= 0 for h in heirs)


def test_rounding_cent_goes_to_biggest_quota():
    a, b, c = split_estate(Decimal("100.00"), _heirs("1/3", "1/3", "1/3"))
    assert (a.share, b.share, c.share) == (Decimal("33.34"), Decimal("33.33"), Decimal("33.33"))


def test_negative_balance_splits_nothing():
    assert [h.share for h in split_estate(Decimal("-50"), _heirs("1/2", "1/2"))] == [0, 0]


# ---------- succesiune ----------

def test_s21_estate_split_on_three_heirs_including_eur_account():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S21"}).json()
    assert case["module_id"] == "insolventa" and case["doc_type"] == "CERTIFICAT_MOSTENITOR"
    assert case["proposed_status"] == "AUTO_PROCESSED" and codes(case) == []
    assert shares(case) == {"POPESCU MARIA": Decimal("3121.88"), "POPESCU ANDREI": Decimal("4682.81"),
                            "IONESCU ELENA": Decimal("4682.82")}
    assert sum(shares(case).values()) == Decimal("12487.51")      # 10.000,01 RON + 500 EUR × 4,9750
    assert "POPESCU ANDREI" in case["outcome"]["response_letter_text"]


def test_s22_wrong_quotas_block_and_late_card_payments_warn():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S22"}).json()
    assert case["status"] == "EXCEPTION_FLAGGED" and codes(case) == ["E05", "E06"]
    assert shares(case) == {}                                      # nu se împarte pe cote greșite
    e06 = [e for e in case["exceptions"] if e["code"] == "E06"]
    assert {tx for e in e06 for tx in e["evidence"]} == {"TX-S22-2", "TX-S22-3"}


def test_officer_override_on_wrong_quotas_does_not_pay_anything():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S22"}).json()
    done = client.post(f"/api/cases/{case['case_id']}/review",
                       json={"reviewer": "ofiter", "resolve_codes": ["E05"]}).json()
    assert done["proposed_status"] == "AUTO_PROCESSED"
    assert "rectificat" in done["outcome"]["response_letter_text"]


def test_certificate_for_living_customer_is_blocked():
    def alive(bank):
        bank["customers"][0]["status"] = "ACTIV"
    assert "E08" in codes(scenario("S21", bank=alive))


def test_certificate_with_invalid_heir_cnp():
    case = scenario("S21", text=lambda t: t.replace("2520618123460", "2520618123461"))
    assert case["status"] == "EXCEPTION_FLAGGED" and "E01" in codes(case) and shares(case) == {}


def test_certificate_with_percent_quotas():
    case = scenario("S21", text=lambda t: t.replace("cotă 1/4", "cotă 25%").replace("cotă 3/8", "cotă 37,5%"))
    assert case["proposed_status"] == "AUTO_PROCESSED" and sum(shares(case).values()) == Decimal("12487.51")


def test_certificate_without_heirs_is_invalid():
    case = scenario("S21", text=lambda t: t.split("Moștenitori")[0] + "semnătura și ștampila notarului L.S.")
    assert case["status"] == "EXCEPTION_FLAGGED" and "E05" in codes(case)


def test_deceased_with_active_garnishment_needs_officer():
    def garnished(bank):
        bank["active_garnishments"].append({
            "garnishment_id": "G-1", "customer_id": "CUST-021", "case_number": "77/2026", "issuer_name": "BEJ X",
            "creditor_name": "ENEL", "creditor_type": "COMERCIAL", "total_due": 1300, "amount_recovered": 0,
            "monthly_periodic_take": 0, "registered_at": "2026-07-01T09:00:00Z"})
    case = scenario("S21", bank=garnished)
    assert case["status"] == "EXCEPTION_FLAGGED" and codes(case) == ["E04"]
    assert "R-SUC-03" in [r["rule_id"] for r in case["decision"]["rules_applied"]]


# ---------- insolvență ----------

def test_s23_insolvency_suspends_garnishments():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S23"}).json()
    assert case["module_id"] == "insolventa" and case["doc_type"] == "NOTIFICARE_INSOLVENTA"
    assert case["proposed_status"] == "AUTO_PROCESSED" and codes(case) == ["E06"]
    assert case["order"]["debtor_id"] == "34567892"                # CUI citit fără prefixul RO
    suspended = [r for r in case["decision"]["rules_applied"] if r["rule_id"] == "R-INS-01"]
    assert len(suspended) == 2 and case["decision"]["amount_to_hold"] == 0
    assert "880/2026" in case["outcome"]["response_letter_text"]


def test_s24_bankruptcy_of_non_client_is_answered_automatically():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S24"}).json()
    assert case["proposed_status"] == "AUTO_PROCESSED" and codes(case) == []
    assert "nu figurează" in case["outcome"]["response_letter_text"]
    assert "EXPERT LICHIDARE SPRL" in case["outcome"]["response_letter_text"]


def test_garnishment_after_insolvency_is_blocked():
    """După notificarea de insolvență, o poprire nouă pe aceeași firmă ia E08, iar popririle vechi nu mai contează."""
    approve(client.post("/api/cases/from-scenario", json={"scenario_id": "S23"}).json())
    s1 = json.loads((config.SCENARIOS_DIR / "S1.json").read_text(encoding="utf-8"))["document"]["text"]
    poprire = scenario("S23", text=lambda _t: s1.replace("IONESCU MIHAI, CNP: 1850615400011",
                                                         "CONSTRUCT PRO SRL, CUI: 34567892"))
    assert poprire["module_id"] == "popriri"
    assert poprire["status"] == "EXCEPTION_FLAGGED" and "E08" in codes(poprire)
    assert (poprire["decision"] or {}).get("amount_to_hold", 0) == 0
    assert poprire["active_garnishments"] == []


def test_rerun_of_insolvency_case_does_not_see_itself():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S23"}).json()
    again = client.post(f"/api/cases/{case['case_id']}/review", json={"reviewer": "x"}).json()
    assert again["proposed_status"] == "AUTO_PROCESSED" and codes(again) == ["E06"]


def test_insolvency_without_stamp_is_blocked():
    case = scenario("S23", text=lambda t: t.replace("Prezenta notificare poartă semnătură și ștampilă L.S.", ""))
    assert case["status"] == "EXCEPTION_FLAGGED" and "E05" in codes(case)


def test_insolvency_with_invalid_insolvency_iban_warns():
    case = scenario("S23", text=lambda t: t.replace("RO76BTRL0000060099990000", "RO77BTRL0000060099990000"))
    assert "E09" in codes(case) and case["proposed_status"] == "AUTO_PROCESSED"


@pytest.mark.parametrize("sid,doc_type", [("S21", "CERTIFICAT_MOSTENITOR"), ("S23", "NOTIFICARE_INSOLVENTA")])
def test_pdf_upload_goes_to_insolvency_module(sid, doc_type):
    pdf = (config.DATA_DIR / "pdfs" / f"{sid}.pdf").read_bytes()
    case = client.post("/api/cases/upload", files={"file": (f"{sid}.pdf", pdf, "application/pdf")},
                       data={"scenario_id": sid}).json()
    assert case["doc_type"] == doc_type and case["module_id"] == "insolventa"
    assert case["proposed_status"] == "AUTO_PROCESSED"


def test_module_is_active():
    mods = {m["module_id"]: m for m in client.get("/api/modules").json()}
    assert mods["insolventa"]["status"] == "ACTIVE"
