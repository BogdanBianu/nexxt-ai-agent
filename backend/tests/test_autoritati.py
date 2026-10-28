"""Teste unitare și de integrare pentru Modulul 2: Cereri Autorități (Poliție / Parchet / DNA — Art. 170 CPP)."""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.contracts import (
    Account, AccountType, BankSnapshot, Case, CaseStatus, Customer, CustomerStatus,
    DocType, ExceptionCode, IncomingDocument, ModuleStatus, ReviewAction, Transaction, TxDirection,
)
from app.core.events import EventSink
from app.core.modules import module_for, registry
from app.main import app

client = TestClient(app)


def _sample_bank() -> BankSnapshot:
    return BankSnapshot(
        customers=[
            Customer(
                customer_id="CUST-008",
                full_name="VASILESCU DANIEL",
                national_id="2901107000013",
                is_legal_entity=False,
                status=CustomerStatus.ACTIV,
                address="Calea Victoriei nr. 100, București",
            )
        ],
        accounts=[
            Account(
                iban="RO49AAAA1B31007593840000",
                customer_id="CUST-008",
                account_type=AccountType.CURENT,
                currency="RON",
                opening_balance=Decimal("10000.00"),
                current_balance=Decimal("45000.00"),
            )
        ],
        transactions=[
            Transaction(
                tx_id="TX-AUTH-1",
                iban="RO49AAAA1B31007593840000",
                booking_date="2026-10-12",
                direction=TxDirection.CREDIT,
                amount=Decimal("35000.00"),
                counterparty_name="SC CONSULTING SRL",
                description="Incasare factura servicii",
            )
        ],
        active_garnishments=[],
    )


def test_autoritati_module_is_active_in_registry():
    mods = registry()
    assert "autoritati" in mods
    assert mods["autoritati"].info.status == ModuleStatus.ACTIVE
    assert DocType.CERERE_AUTORITATE in mods["autoritati"].info.handled_doc_types
    assert module_for(DocType.CERERE_AUTORITATE) is mods["autoritati"]


def test_s8_igpr_request_processes_end_to_end():
    res = client.post("/api/cases/from-scenario", json={"scenario_id": "S8"})
    assert res.status_code == 200, res.text
    case = res.json()
    assert case["module_id"] == "autoritati"
    assert case["doc_type"] == "CERERE_AUTORITATE"
    assert case["proposed_status"] == "AUTO_PROCESSED"
    assert case["order"]["case_number"] == "445566/P/2026"
    assert case["order"]["debtor_name"] == "VASILESCU DANIEL"
    assert case["order"]["debtor_id"] == "2901107000013"
    assert case["decision"]["amount_to_hold"] == 0.0
    assert case["decision"]["amount_protected"] == 45000.0
    assert any(r["rule_id"] == "R-CPP-170" for r in case["decision"]["rules_applied"])
    assert "CONFIDENȚIAL — SECRET BANCAR" in case["outcome"]["response_letter_text"]
    assert "445566/P/2026" in case["outcome"]["response_letter_text"]


def test_autoritati_blocks_disclosure_without_legal_basis():
    """Fără invocarea Art. 170 CPP / ordonanță procuror, secretul bancar oprește divulgarea automată (E05)."""
    now = datetime.now(timezone.utc)
    doc = IncomingDocument(
        document_id="DOC-NO-BASIS",
        filename="adresa_incompleta_politie.txt",
        received_at=now,
        text=(
            "INSPECTORATUL DE POLIȚIE JUDEȚEAN CLUJ\n"
            "Dosar penal nr. 112/P/2026\n"
            "Data: 20.10.2026\n\n"
            "Vă solicităm comunicarea conturilor pentru:\n"
            "Nume: VASILESCU DANIEL, CNP: 2901107000013\n"
            "Semnătură și ștampilă L.S."
        ),
    )
    case = Case(
        case_id="CASE-AUTH-NOBASIS",
        doc_type=DocType.CERERE_AUTORITATE,
        status=CaseStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        document=doc,
    )
    sink = EventSink(case.case_id)
    processed = module_for(DocType.CERERE_AUTORITATE).process(case, _sample_bank(), sink.emit)
    assert processed.status == CaseStatus.EXCEPTION_FLAGGED
    codes = {e.code for e in processed.exceptions if not e.resolved}
    assert ExceptionCode.E05_DOCUMENT_INVALID in codes
    assert processed.outcome.response_letter_text is None

    # După aprobarea ofițerului juridic în HITL Workbench, se generează răspunsul
    review = ReviewAction(reviewer="ofiter.juridic@raiffeisen.ro", resolve_codes=["E05"], note="Ordonanță atașată în anexă")
    after_review = module_for(DocType.CERERE_AUTORITATE).process(processed, _sample_bank(), sink.emit, review=review)
    assert after_review.status == CaseStatus.AUTO_PROCESSED
    assert after_review.outcome.response_letter_text is not None


def test_autoritati_flags_invalid_cnp_with_e01():
    now = datetime.now(timezone.utc)
    doc = IncomingDocument(
        document_id="DOC-BAD-CNP",
        filename="adresa_igpr_cnp_gresit.txt",
        received_at=now,
        text=(
            "INSPECTORATUL GENERAL AL POLIȚIEI ROMÂNE\n"
            "Dosar penal nr. 999/P/2026\n"
            "Data: 20.10.2026\n"
            "În baza art. 170 Cod Procedură Penală solicităm rulajele pentru:\n"
            "Nume: VASILESCU DANIEL, CNP: 2901107000019\n"
            "Semnătură și ștampilă L.S."
        ),
    )
    case = Case(
        case_id="CASE-AUTH-BADCNP",
        doc_type=DocType.CERERE_AUTORITATE,
        status=CaseStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        document=doc,
    )
    sink = EventSink(case.case_id)
    processed = module_for(DocType.CERERE_AUTORITATE).process(case, _sample_bank(), sink.emit)
    assert processed.status == CaseStatus.EXCEPTION_FLAGGED
    assert any(e.code == ExceptionCode.E01_IDENTITATE for e in processed.exceptions)
