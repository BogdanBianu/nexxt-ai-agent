"""Sechestre: emitentul corect, rutarea din router și tipul măsurii trimis frontend-ului. Proprietar: Om2."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.modules.sechestre.extractor import match_issuer

client = TestClient(app)


def test_prosecutor_is_not_mistaken_for_civil_court():
    """„Parchetul de pe lângă Tribunalul București” conține și „Tribunalul București” (emitentul civil din registru)."""
    issuer = match_issuer("MINISTERUL PUBLIC — PARCHETUL DE PE LANGA TRIBUNALUL BUCURESTI ORDONANTA")
    assert issuer["issuer_id"] == "AUT-PTB-MP"
    assert match_issuer("TRIBUNALUL BUCURESTI SECTIA A VI-A CIVILA")["issuer_id"] == "AUT-TB-S6"


@pytest.mark.parametrize("sid,doc_type,measure,issuer", [
    ("S17", "SECHESTRU_INSTITUIRE", "SECHESTRU_ASIGURATOR_FISCAL", "ANTIFRAUDĂ"),
    ("S18", "SECHESTRU_INSTITUIRE", "SECHESTRU_ASIGURATOR_CIVIL", "TRIBUNALUL BUCUREȘTI"),
    ("S19", "SECHESTRU_INSTITUIRE", "SECHESTRU_ASIGURATOR_PENAL", "PARCHETUL"),
    ("S20", "SECHESTRU_RIDICARE", "SECHESTRU_ASIGURATOR_FISCAL", "ANTIFRAUDĂ"),
])
def test_seizure_routing_issuer_and_measure(sid, doc_type, measure, issuer):
    case = client.post("/api/cases/from-scenario", json={"scenario_id": sid}).json()
    assert case["module_id"] == "sechestre" and case["doc_type"] == doc_type
    assert issuer in case["order"]["issuer_name"]
    assert case["order"]["measure_type"] == measure and case["order"]["legal_basis"]
    router = [e for e in client.get(f"/api/cases/{case['case_id']}/events").json() if e["agent"] == "INTAKE_ROUTER"]
    assert "→ sechestre" in router[-1]["message"] and "PopririZero" not in router[-1]["message"]


def test_poprire_with_seizure_scenario_number_stays_in_popriri():
    """Rutarea nu mai depinde de numărul scenariului: o poprire încărcată pe banca S17 rămâne poprire."""
    text = main.load_scenario("S1").document.text
    case = client.post("/api/cases/upload", files={"file": ("poprire.txt", text.encode("utf-8"), "text/plain")},
                       data={"scenario_id": "S17"}).json()
    assert case["module_id"] == "popriri" and case["doc_type"] == "POPRIRE_INFIINTARE"
