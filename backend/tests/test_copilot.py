"""Agentul „Explain & Cite”: POST /api/cases/{case_id}/ask răspunde din dosar și citează legea + tranzacțiile."""
from fastapi.testclient import TestClient

from app.core import llm
from app.main import app

client = TestClient(app)


def _case(scenario_id: str) -> dict:
    return client.post("/api/cases/from-scenario", json={"scenario_id": scenario_id}).json()


def _ask(case_id: str, question: str, **extra) -> dict:
    res = client.post(f"/api/cases/{case_id}/ask", json={"question": question, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def test_popriri_question_cites_rules_legal_source_and_transactions(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    case = _case("S1")
    ans = _ask(case["case_id"], "De ce nu i-ați poprit toți banii din contul RO49...?")
    assert ans["method"] == "DETERMINISTIC"
    refs = {c["ref"] for c in ans["citations"]}
    assert {"R-WAGE-04", "R-EXEMPT-01"} <= refs
    wage = next(c for c in ans["citations"] if c["ref"] == "R-WAGE-04")
    assert wage["legal_source"] == "CPC art. 729 alin. (1) lit. b)" and wage["tx_ids"] == ["TX-1001"]
    assert "CPC art. 729 alin. (1) lit. b)" in ans["answer"] and "TX-1001" in ans["answer"]
    assert "5800.00 RON" in ans["answer"]


def test_gdpr_erasure_question_cites_aml_retention(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    case = _case("S26")
    ans = _ask(case["case_id"], "De ce nu ștergem datele lui Popescu dacă a invocat Art. 17 GDPR?")
    assert ans["citations"][0]["ref"] == "R-GDPR-AML-17"
    assert "Legea 129/2019" in ans["answer"]


def test_flagged_case_explains_the_blocking_exception(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    case = _case("S4")
    ans = _ask(case["case_id"], "De ce nu s-a blocat nimic?")
    exc = next(c for c in ans["citations"] if c["kind"] == "EXCEPTION")
    assert exc["ref"] == "E06" and exc["tx_ids"] == ["TX-S4-10"]
    assert "blocantă, nerezolvată" in ans["answer"]


def test_transaction_id_in_question_is_cited_first(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    case = _case("S1")
    ans = _ask(case["case_id"], "Cum ați clasificat TX-1002?")
    assert ans["citations"][0]["ref"] == "TX-1002"


def test_llm_answer_keeps_only_citations_that_exist_in_the_case(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {
        "answer": "Din salariu se poate popri doar 1/3 (CPC art. 729 alin. (1) lit. b)).",
        "citations": ["R-WAGE-04", "TX-1001", "R-INVENTAT-99"]})
    case = _case("S1")
    ans = _ask(case["case_id"], "De ce doar o treime din salariu?")
    assert ans["method"] == "LLM"
    assert [c["ref"] for c in ans["citations"]] == ["R-WAGE-04", "TX-1001"]


def test_llm_answer_without_valid_citations_falls_back_to_case_facts(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {
        "answer": "Conform art. 999 din Legea inventată, nu se poprește nimic.", "citations": ["ART-999"]})
    case = _case("S1")
    ans = _ask(case["case_id"], "De ce s-a blocat suma?")
    assert ans["method"] == "DETERMINISTIC"
    assert "art. 999" not in ans["answer"] and ans["citations"]


def test_question_is_written_to_audit_trail(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    case = _case("S1")
    _ask(case["case_id"], "De ce TX-1002 nu a fost poprită?", asked_by="ofiter@test.ro")
    audit = client.get(f"/api/cases/{case['case_id']}/audit").json()
    entry = next(a for a in audit if a["action"] == "COPILOT_QUESTION")
    assert entry["actor"] == "user:ofiter@test.ro"
    assert entry["details"]["question"] == "De ce TX-1002 nu a fost poprită?"
    assert "TX-1002" in entry["details"]["citations"]


def test_routed_document_gets_an_answer_without_citations(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    text = "Către Raiffeisen Bank\nInvitație la conferința anuală a asociației băncilor din 12.11.2026."
    case = client.post("/api/cases/upload", files={"file": ("inv.txt", text.encode("utf-8"), "text/plain")},
                       data={"scenario_id": "S1"}).json()
    ans = _ask(case["case_id"], "De ce nu s-a procesat?")
    assert ans["citations"] == [] and "ROUTED_TO_OTHER_MODULE" in ans["answer"]


def test_unknown_case_and_empty_question_are_rejected():
    assert client.post("/api/cases/CASE-NU-EXISTA/ask", json={"question": "De ce?"}).status_code == 404
    case = _case("S1")
    assert client.post(f"/api/cases/{case['case_id']}/ask", json={"question": ""}).status_code == 422
