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
