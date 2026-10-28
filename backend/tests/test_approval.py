"""Aprobarea umană: agentul doar marchează dosarul „conform”, iar un angajat îl aprobă sau îl respinge."""
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def new_case(scenario_id: str) -> dict:
    return client.post("/api/cases/from-scenario", json={"scenario_id": scenario_id}).json()


def approve(case_id: str, **body):
    return client.post(f"/api/cases/{case_id}/approve", json={"reviewer": "ofiter@test.ro", **body})


def reject(case_id: str, **body):
    return client.post(f"/api/cases/{case_id}/reject", json={"reviewer": "ofiter@test.ro", **body})


def test_agent_only_proposes_a_compliant_case():
    case = new_case("S1")
    assert case["status"] == "PENDING_APPROVAL" and case["proposed_status"] == "AUTO_PROCESSED"
    assert case["approval"] is None
    assert client.get(f"/api/cases/{case['case_id']}/response-pdf").status_code == 409


def test_employee_approval_issues_the_hold_and_the_response():
    case = new_case("S1")
    res = approve(case["case_id"], note="Verificat, conform")
    assert res.status_code == 200
    done = res.json()
    assert done["status"] == "AUTO_PROCESSED"
    assert done["approval"]["decision"] == "APPROVED" and done["approval"]["reviewer"] == "ofiter@test.ro"
    assert done["approval"]["previous_status"] == "PENDING_APPROVAL"
    assert client.get(f"/api/cases/{case['case_id']}/response-pdf").status_code == 200
    audit = client.get(f"/api/cases/{case['case_id']}/audit").json()
    entry = next(a for a in audit if a["action"] == "CASE_APPROVED")
    assert entry["actor"] == "user:ofiter@test.ro" and entry["details"]["note"] == "Verificat, conform"


def test_lifting_is_also_approved_by_an_employee():
    case = new_case("S7")
    assert case["status"] == "PENDING_APPROVAL" and case["proposed_status"] == "LIFTED"
    assert approve(case["case_id"]).json()["status"] == "LIFTED"


def test_employee_can_reject_with_a_reason():
    case = new_case("S1")
    res = reject(case["case_id"], note="Adresa nu poartă ștampila originală")
    assert res.status_code == 200
    done = res.json()
    assert done["status"] == "REJECTED" and done["approval"]["decision"] == "REJECTED"
    assert client.get(f"/api/cases/{case['case_id']}/response-pdf").status_code == 409
    audit = client.get(f"/api/cases/{case['case_id']}/audit").json()
    assert any(a["action"] == "CASE_REJECTED" for a in audit)


def test_reject_requires_a_reason():
    case = new_case("S1")
    assert reject(case["case_id"]).status_code == 422
    assert reject(case["case_id"], note="   ").status_code == 422
    assert client.get(f"/api/cases/{case['case_id']}").json()["status"] == "PENDING_APPROVAL"


def test_flagged_case_can_be_rejected_but_not_approved():
    case = new_case("S4")
    assert case["status"] == "EXCEPTION_FLAGGED"
    assert approve(case["case_id"]).status_code == 409
    done = reject(case["case_id"], note="Diurnă deghizată confirmată, se returnează executorului").json()
    assert done["status"] == "REJECTED" and done["approval"]["previous_status"] == "EXCEPTION_FLAGGED"


def test_decision_is_final():
    case = new_case("S1")
    approve(case["case_id"])
    assert approve(case["case_id"]).status_code == 409
    assert reject(case["case_id"], note="m-am răzgândit").status_code == 409
    review = client.post(f"/api/cases/{case['case_id']}/review", json={"reviewer": "x"})
    assert review.status_code == 409


def test_hitl_review_still_ends_in_pending_approval():
    case = new_case("S4")
    review = {"reviewer": "ofiter", "overrides": [{"tx_id": "TX-S4-10", "category": "SALARIU"}],
              "resolve_codes": ["E06"]}
    after = client.post(f"/api/cases/{case['case_id']}/review", json=review).json()
    assert after["status"] == "PENDING_APPROVAL" and after["proposed_status"] == "AUTO_PROCESSED"
    assert approve(case["case_id"]).json()["status"] == "AUTO_PROCESSED"


def test_rejected_garnishment_is_not_registered():
    """O poprire respinsă nu intră în registru: aceeași adresă trimisă din nou nu e duplicat (E02)."""
    first = new_case("S1")
    reject(first["case_id"], note="Respins")
    again = new_case("S1")
    assert again["proposed_status"] == "AUTO_PROCESSED" and again["exceptions"] == []


def test_pending_garnishment_reserves_its_place():
    """Două adrese identice în așteptare: a doua e duplicat, ca să nu poată fi aprobate amândouă."""
    new_case("S1")                                   # încă neaprobat
    again = new_case("S1")
    assert again["status"] == "EXCEPTION_FLAGGED" and [e["code"] for e in again["exceptions"]] == ["E02"]


def test_pending_lifting_does_not_free_the_garnishment(monkeypatch):
    """O sistare neaprobată (sau respinsă) nu scoate poprirea din registru."""
    import json
    from app import config
    from app.contracts import Scenario
    first = new_case("S1")
    approve(first["case_id"])
    raw = json.loads((config.SCENARIOS_DIR / "S1.json").read_text(encoding="utf-8"))
    raw["document"]["text"] = (raw["document"]["text"].replace("ÎNFIINȚARE A POPRIRII", "SISTARE A POPRIRII")
                               .replace("ÎNFIINȚAREA POPRIRII", "SISTAREA POPRIRII"))
    variant = Scenario.model_validate(raw)
    monkeypatch.setattr(main, "load_scenario", lambda sid: variant)
    lifting = new_case("S1")
    assert lifting["proposed_status"] == "LIFTED"
    reject(lifting["case_id"], note="Sistare neconfirmată de executor")
    monkeypatch.undo()
    again = new_case("S1")
    assert [e["code"] for e in again["exceptions"]] == ["E02"]   # poprirea e încă activă


def test_routed_case_cannot_be_approved_or_rejected():
    text = "Către Raiffeisen Bank\nInvitație la conferința anuală a asociației băncilor din 12.11.2026."
    case = client.post("/api/cases/upload", files={"file": ("inv.txt", text.encode("utf-8"), "text/plain")},
                       data={"scenario_id": "S1"}).json()
    assert approve(case["case_id"]).status_code == 409
    assert reject(case["case_id"], note="x").status_code == 409


def test_unknown_case_returns_404():
    assert approve("CASE-NU-EXISTA").status_code == 404


def test_metrics_count_money_only_after_approval(monkeypatch):
    monkeypatch.setattr(main, "CASES", {})
    pending = new_case("S1")
    m = client.get("/api/metrics").json()
    assert m["total_amount_held"] == 0 and m["automation_rate"] == 100.0   # agentul a propus fără om
    assert m["cases_by_status"] == {"PENDING_APPROVAL": 1}
    approve(pending["case_id"])
    assert client.get("/api/metrics").json()["total_amount_held"] == 5800.0
