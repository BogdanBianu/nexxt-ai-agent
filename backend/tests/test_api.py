"""Teste pentru endpoint-urile FastAPI ale lui Om2: rules, metrics, upload, response-pdf."""
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def approve(case: dict) -> dict:
    """Angajatul aprobă propunerea agentului: abia atunci poprirea / insolvența intră în registru."""
    res = client.post(f"/api/cases/{case['case_id']}/approve", json={"reviewer": "ofiter"})
    assert res.status_code == 200, res.text
    return res.json()


def test_rules_endpoint_exposes_registry():
    res = client.get("/api/rules")
    assert res.status_code == 200
    body = res.json()
    ids = [r["id"] for r in body["rules"]]
    assert "R-PRIO-09" in ids and body["version"] == "2026.10"
    assert body["parameters"]["creditor_priority"] == ["INTRETINERE", "FISCAL", "COMERCIAL"]


def test_upload_txt_runs_pipeline_and_feeds_metrics():
    text = main.load_scenario("S1").document.text
    res = client.post("/api/cases/upload", files={"file": ("adresa.txt", text.encode("utf-8"), "text/plain")},
                      data={"scenario_id": "S1"})
    assert res.status_code == 200, res.text
    case = res.json()
    assert case["case_id"].startswith("CASE-UP-")
    assert case["proposed_status"] == "AUTO_PROCESSED"
    assert case["decision"]["amount_to_hold"] == 5800.0
    assert client.get(f"/api/cases/{case['case_id']}/response-pdf").status_code == 409   # încă neaprobat
    assert approve(case)["status"] == "AUTO_PROCESSED"

    metrics = client.get("/api/metrics").json()
    assert metrics["total_cases"] >= 1
    assert metrics["total_amount_held"] >= 5800.0
    assert metrics["automation_rate"] > 0

    pdf = client.get(f"/api/cases/{case['case_id']}/response-pdf")
    assert pdf.status_code == 200
    assert "RAIFFEISEN" in pdf.content.decode("utf-8", errors="ignore") or pdf.content[:5] == b"%PDF-"


def test_upload_auto_detects_customer_bank_without_scenario_pairing():
    """La upload fără scenario_id (sau cu AUTO), backend-ul găsește singur persoana în memorie (ex. S4 DUMITRU ALEXANDRU)."""
    text_s4 = main.load_scenario("S4").document.text
    res = client.post("/api/cases/upload", files={"file": ("document_email.txt", text_s4.encode("utf-8"), "text/plain")})
    assert res.status_code == 200, res.text
    case = res.json()
    assert case["scenario_id"] == "S4"
    assert case["customer"]["full_name"] == "DUMITRU ALEXANDRU"
    assert case["status"] == "EXCEPTION_FLAGGED"


def test_upload_rejects_unsupported_files():
    res = client.post("/api/cases/upload", files={"file": ("poza.png", b"\x89PNG....", "image/png")})
    assert res.status_code == 415


def test_response_pdf_conflict_when_case_flagged():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S4"}).json()
    assert case["status"] == "EXCEPTION_FLAGGED"
    assert client.get(f"/api/cases/{case['case_id']}/response-pdf").status_code == 409


def test_audit_trail_has_agents_rules_and_hitl_review():
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S4"}).json()
    review = {"reviewer": "ofiter@test.ro", "overrides": [{"tx_id": "TX-S4-10", "category": "SALARIU"}],
              "resolve_codes": ["E06"]}
    assert client.post(f"/api/cases/{case['case_id']}/review", json=review).json()["proposed_status"] == "AUTO_PROCESSED"

    audit = client.get(f"/api/cases/{case['case_id']}/audit").json()
    actions = {a["action"] for a in audit}
    assert {"STARTED", "COMPLETED", "RULE_APPLIED", "EXCEPTION_RAISED", "HITL_REVIEW"} <= actions
    assert any(a["actor"] == "user:ofiter@test.ro" for a in audit)


def test_sistare_keeps_router_doc_type_through_langgraph():
    """S7: tipul stabilit de router (sistare) trebuie să ajungă la agenți; altfel e tratat ca înființare (E02/E09)."""
    case = client.post("/api/cases/from-scenario", json={"scenario_id": "S7"}).json()
    assert case["doc_type"] == "POPRIRE_SISTARE"
    assert case["order"]["doc_type"] == "POPRIRE_SISTARE"
    assert case["proposed_status"] == "LIFTED"
    assert case["exceptions"] == []


def test_routed_document_marks_popriri_agents_skipped():
    """Un document de tip necunoscut: router-ul îl redirecționează către un ofițer, iar agenții apar SKIPPED."""
    text = "Către Raiffeisen Bank\nInvitație la conferința anuală a asociației băncilor din 12.11.2026."
    case = client.post("/api/cases/upload", files={"file": ("invitatie.txt", text.encode("utf-8"), "text/plain")},
                       data={"scenario_id": "S1"}).json()
    assert case["status"] == "ROUTED_TO_OTHER_MODULE"
    last = {}
    for ev in client.get(f"/api/cases/{case['case_id']}/events").json():
        last[ev["agent"]] = ev
    assert "redirecționat" in last["INTAKE_ROUTER"]["message"]
    assert all(last[a]["status"] == "SKIPPED" for a in
               ["EXTRACTION", "RECONCILIATION", "INCOME_CLASSIFIER", "RULE_ENGINE", "ANOMALY", "OUTCOME"])
