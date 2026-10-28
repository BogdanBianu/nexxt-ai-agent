"""Teste unitare și de integrare pentru Modulul 3: Cereri GDPR (Regulamentul UE 2016/679 & ANSPDCP)."""
from datetime import datetime, timezone
from decimal import Decimal

from app.contracts import (
    Account, AccountType, ActiveGarnishment, BankSnapshot, Case, CaseStatus, CreditorType,
    Customer, CustomerStatus, DocType, ExceptionCode, IncomingDocument, ModuleStatus,
    ReviewAction, Severity, Transaction, TxDirection,
)
from app.core.events import EventSink
from app.core.modules import module_for, registry
from app.core.router import classify_document
from app.modules.gdpr.module import GdprModule


def _gdpr_bank(with_active_garnishment: bool = False) -> BankSnapshot:
    garnishments = []
    if with_active_garnishment:
        garnishments.append(ActiveGarnishment(
            garnishment_id="G-TEST-001",
            customer_id="CUST-GDPR-1",
            case_number="889/2026",
            issuer_name="BEJ IONESCU RADU",
            creditor_name="BANCA COMERCIALA S.A.",
            creditor_type=CreditorType.COMERCIAL,
            total_due=Decimal("15000.00"),
            monthly_periodic_take=Decimal("1500.00"),
            registered_at=datetime.now(timezone.utc),
        ))

    return BankSnapshot(
        customers=[
            Customer(
                customer_id="CUST-GDPR-1",
                full_name="POPESCU ION",
                national_id="1850615400011",
                is_legal_entity=False,
                status=CustomerStatus.ACTIV,
                address="Str. Mihai Eminescu nr. 12, București",
            )
        ],
        accounts=[
            Account(
                iban="RO49RZBR0000060012345678",
                customer_id="CUST-GDPR-1",
                account_type=AccountType.CURENT,
                currency="RON",
                opening_balance=Decimal("2000.00"),
                current_balance=Decimal("8500.00"),
            )
        ],
        transactions=[
            Transaction(
                tx_id="TX-GDPR-1",
                iban="RO49RZBR0000060012345678",
                booking_date="2026-10-15",
                direction=TxDirection.CREDIT,
                amount=Decimal("6500.00"),
                counterparty_name="ANGAPROD SRL",
                description="Salariu luna septembrie",
            )
        ],
        active_garnishments=garnishments,
    )


def test_gdpr_module_is_active_in_registry():
    mods = registry()
    assert "gdpr" in mods
    assert mods["gdpr"].info.status == ModuleStatus.ACTIVE
    assert DocType.CERERE_GDPR in mods["gdpr"].info.handled_doc_types
    assert module_for(DocType.CERERE_GDPR) is mods["gdpr"]


def test_router_classifies_gdpr_requests():
    sink = EventSink("TEST-ROUTER")
    doc_access = IncomingDocument(
        document_id="DOC-R1",
        filename="cerere_acces.txt",
        received_at=datetime.now(timezone.utc),
        text="Subsemnatul Popescu Ion, solicit în baza Regulamentului (UE) 2016/679 dreptul de acces la datele mele.",
    )
    doc_type, conf, reason = classify_document(doc_access, sink.emit)
    assert doc_type == DocType.CERERE_GDPR
    assert conf >= 0.9

    doc_erasure = IncomingDocument(
        document_id="DOC-R2",
        filename="cerere_stergere.txt",
        received_at=datetime.now(timezone.utc),
        text="Solicit stergerea datelor cu caracter personal si dreptul de a fi uitat conform GDPR.",
    )
    doc_type, conf, reason = classify_document(doc_erasure, sink.emit)
    assert doc_type == DocType.CERERE_GDPR


def test_gdpr_access_request_processes_autonomously():
    """Art. 15 GDPR: Furnizare raport date fără blocare de sume (0.00 RON hold)."""
    now = datetime.now(timezone.utc)
    doc = IncomingDocument(
        document_id="DOC-GDPR-ACC",
        filename="cerere_acces_date.txt",
        received_at=now,
        text="""CERERE DE EXERCITARE A DREPTULUI DE ACCES (Art. 15 GDPR)
Data: 20.10.2026
Către: RAIFFEISEN BANK S.A.

Subsemnatul POPESCU ION, CNP: 1850615400011, client al băncii dumneavoastră,
în temeiul art. 15 din Regulamentul (UE) 2016/679, vă solicit să-mi comunicați:
1. Categoriile de date cu caracter personal prelucrate;
2. Scopurile prelucrării și destinatarii cărora le-au fost transmise datele;
3. Copia datelor financiare și a conturilor deschise pe numele meu.

Semnătură olografă: Popescu Ion (L.S.)""",
    )
    case = Case(
        case_id="CASE-GDPR-01",
        doc_type=DocType.CERERE_GDPR,
        status=CaseStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        document=doc,
    )
    sink = EventSink(case.case_id)
    mod = GdprModule()
    result = mod.process(case, _gdpr_bank(), sink.emit)

    assert result.status == CaseStatus.AUTO_PROCESSED
    assert result.decision.amount_to_hold == Decimal("0.00")
    assert result.decision.amount_protected == Decimal("8500.00")
    assert any(r.rule_id == "R-GDPR-ACC-15" for r in result.decision.rules_applied)
    assert result.outcome.response_letter_text is not None
    assert "DREPTUL DE ACCES (Art. 15 GDPR): Cererea dumneavoastră a fost APROBATĂ" in result.outcome.response_letter_text
    assert "RO49RZBR0000060012345678" in result.outcome.response_letter_text


def test_gdpr_erasure_request_applies_aml_retention_rule():
    """Art. 17 GDPR vs Legea 129/2019 (AML): Refuz parțial motivat pe păstrarea 5 ani a datelor tranzacționale."""
    now = datetime.now(timezone.utc)
    doc = IncomingDocument(
        document_id="DOC-GDPR-DEL",
        filename="cerere_dreptul_de_a_fi_uitat.txt",
        received_at=now,
        text="""CERERE PRIVIND ȘTERGEREA DATELOR („DREPTUL DE A FI UITAT” - Art. 17 GDPR)
Nr. înregistrare: 778/2026
Data: 22.10.2026

Subsemnatul POPESCU ION, CNP: 1850615400011, solicit ștergerea definitivă a tuturor
datelor mele din evidențele băncii, istoricul tranzacțiilor și bazele de date de marketing.
Semnătură și trimitere prin Smart Mobile.""",
    )
    case = Case(
        case_id="CASE-GDPR-02",
        doc_type=DocType.CERERE_GDPR,
        status=CaseStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        document=doc,
    )
    sink = EventSink(case.case_id)
    mod = GdprModule()
    result = mod.process(case, _gdpr_bank(), sink.emit)

    assert result.status == CaseStatus.AUTO_PROCESSED
    assert result.decision.amount_to_hold == Decimal("0.00")
    assert any(r.rule_id == "R-GDPR-AML-17" for r in result.decision.rules_applied)
    letter = result.outcome.response_letter_text
    assert "Legea nr. 129/2019 pentru prevenirea spălării banilor (AML)" in letter
    assert "Timp de 5 ANI" in letter
    assert "PRIVIND PRELUCRAREA ÎN SCOP DE MARKETING ȘI PROFILARE COMERCIALĂ: APROBAT" in letter


def test_gdpr_erasure_flags_evasion_when_active_garnishment_exists():
    """Dacă un debitor cu poprire activă cere ștergerea datelor, sistemul ridică E06_SUSPICIUNE_ELUDARE."""
    now = datetime.now(timezone.utc)
    doc = IncomingDocument(
        document_id="DOC-GDPR-EVADE",
        filename="cerere_stergere_debitor.txt",
        received_at=now,
        text="""CERERE DE ȘTERGERE A DATELOR CU CARACTER PERSONAL
Data: 25.10.2026
Subsemnatul POPESCU ION, CNP: 1850615400011, solicit ștergerea urgentă a tuturor conturilor și evidențelor mele.
Semnătură L.S.""",
    )
    case = Case(
        case_id="CASE-GDPR-03",
        doc_type=DocType.CERERE_GDPR,
        status=CaseStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        document=doc,
    )
    sink = EventSink(case.case_id)
    mod = GdprModule()
    # Rulăm pe o bancă unde debitorul are poprire activă (dosar 889/2026)
    result = mod.process(case, _gdpr_bank(with_active_garnishment=True), sink.emit)

    assert result.status == CaseStatus.EXCEPTION_FLAGGED
    e06 = next((e for e in result.exceptions if e.code == ExceptionCode.E06_SUSPICIUNE_ELUDARE), None)
    assert e06 is not None
    assert e06.severity == Severity.BLOCKING
    assert "889/2026" in e06.message

    # Test HITL Review: DPO confirmă menținerea evidențelor și respinge eludarea
    review = ReviewAction(
        reviewer="dpo@raiffeisen.ro",
        resolve_codes=["E06"],
        note="Verificat: clientul are poprire activă la BEJ Ionescu. Cererea de ștergere a fost respinsă conform Art. 17 alin. (3) lit. (e) GDPR.",
    )
    resolved_case = mod.process(case, _gdpr_bank(with_active_garnishment=True), sink.emit, review=review)
    assert resolved_case.status == CaseStatus.AUTO_PROCESSED
    assert resolved_case.outcome.response_letter_text is not None


def test_gdpr_invalid_cnp_raises_e01():
    """Un CNP matematic invalid ridică E01_IDENTITATE și oprește căutarea în bancă."""
    now = datetime.now(timezone.utc)
    doc = IncomingDocument(
        document_id="DOC-GDPR-BAD-CNP",
        filename="cerere_cnp_gresit.txt",
        received_at=now,
        text="Subsemnatul POPESCU ION, CNP: 1850615400012, solicit dreptul de acces.",
    )
    case = Case(
        case_id="CASE-GDPR-04",
        doc_type=DocType.CERERE_GDPR,
        status=CaseStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        document=doc,
    )
    sink = EventSink(case.case_id)
    mod = GdprModule()
    result = mod.process(case, _gdpr_bank(), sink.emit)

    assert result.status == CaseStatus.EXCEPTION_FLAGGED
    assert any(e.code == ExceptionCode.E01_IDENTITATE for e in result.exceptions)


# ---------- reparații după revizuire (Om2): nu trebuie să revină ----------

from fastapi.testclient import TestClient  # noqa: E402

from app import main as app_main  # noqa: E402

api = TestClient(app_main.app)


def _upload(text: str, scenario_id: str) -> dict:
    return api.post("/api/cases/upload", files={"file": ("cerere.txt", text.encode("utf-8"), "text/plain")},
                    data={"scenario_id": scenario_id}).json()


def test_access_request_without_signature_does_not_disclose_bank_data():
    """Oricine știe numele și CNP-ul cuiva ar primi IBAN-urile și soldurile lui (Art. 12 alin. 6 GDPR)."""
    text = app_main.load_scenario("S25").document.text.replace("Semnătură olografă: Popescu Ion (L.S.)", "")
    case = _upload(text, "S25")
    assert case["status"] == "EXCEPTION_FLAGGED"
    assert any(e["code"] == "E05" and e["severity"] == "BLOCKING" for e in case["exceptions"])
    assert case["outcome"]["response_letter_text"] is None


def test_gdpr_footer_on_garnishment_does_not_hijack_routing():
    text = app_main.load_scenario("S1").document.text + \
        "\nDatele sunt prelucrate conform Regulamentului (UE) 2016/679 (GDPR) și pot fi sesizate la ANSPDCP."
    case = _upload(text, "S1")
    assert case["module_id"] == "popriri" and case["doc_type"] == "POPRIRE_INFIINTARE"


def test_registration_number_is_read_correctly():
    case = api.post("/api/cases/from-scenario", json={"scenario_id": "S26"}).json()
    assert case["order"]["case_number"] == "GDPR-2026-789"


def test_client_mentioning_anspdcp_stays_a_client_request():
    text = app_main.load_scenario("S25").document.text.replace(
        "titular de cont bancar", "titular de cont bancar (știu că pot sesiza ANSPDCP)")
    case = _upload(text, "S25")
    assert case["order"]["issuer_type"] == "PERSOANA_FIZICA" and case["proposed_status"] == "AUTO_PROCESSED"
    assert "DREPTUL DE ACCES" in case["outcome"]["response_letter_text"]


def test_request_from_anspdcp_letterhead_is_recognized():
    text = ("AUTORITATEA NAȚIONALĂ DE SUPRAVEGHERE A PRELUCRĂRII DATELOR CU CARACTER PERSONAL\n"
            "Nr. adresă: 8812/2026\nData: 27.10.2026\nCătre: RAIFFEISEN BANK S.A.\n"
            "Solicităm evidențele prelucrării datelor pentru persoana vizată:\n"
            "Persoana vizată: POPESCU ION, CNP: 1850615400011\nSemnătură electronică calificată")
    case = _upload(text, "S25")
    assert case["module_id"] == "gdpr" and case["order"]["issuer_type"] == "ANSPDCP"
    assert case["order"]["case_number"] == "8812/2026"
