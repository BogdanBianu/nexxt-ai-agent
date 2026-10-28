"""Schelet de teste unitare pentru Motorul de Reguli și Validatoare. Proprietar: Om2.

Rulare:
    pytest backend/tests
"""
from decimal import Decimal

from app.contracts import (
    ClassificationMethod, ClassifiedTransaction, CreditorType, DocType,
    GarnishmentOrder, IncomeCategory, IssuerType,
)
from app.core.validators import validate_cnp, validate_iban
from app.modules.popriri.engine.calculator import compute_decision
from app.modules.popriri.engine.rules import load_rulebook


def test_validators_cnp_and_iban():
    assert validate_cnp("1850615400016") is True
    assert validate_cnp("1850615400019") is False  # cifră de control greșită
    assert validate_iban("RO49AAAA1B31007593840000") is True
    assert validate_iban("RO00AAAA1B31007593840000") is False


def test_calculator_protects_alocatie_and_takes_one_third_salary():
    book = load_rulebook()
    order = GarnishmentOrder(
        doc_type=DocType.POPRIRE_INFIINTARE,
        issuer_name="BEJ Test",
        issuer_type=IssuerType.EXECUTOR,
        case_number="1/2026",
        issue_date=None,
        debtor_name="IONESCU MIHAI",
        debtor_id="1850615400016",
        creditor_name="Creditor SRL",
        creditor_type=CreditorType.COMERCIAL,
        principal=Decimal("10000"),
        enforcement_costs=Decimal("0"),
        total_due=Decimal("10000"),
        has_signature_and_stamp=True,
    )
    txs = [
        ClassifiedTransaction(
            tx_id="T1", iban="RO49AAAA1B31007593840000", booking_date="2026-10-15",
            amount=Decimal("6000"), counterparty_name="ANGAJATOR", description="Salariu",
            category=IncomeCategory.SALARIU, method=ClassificationMethod.KEYWORD,
            confidence=0.95, rationale="test",
        ),
        ClassifiedTransaction(
            tx_id="T2", iban="RO49AAAA1B31007593840000", booking_date="2026-10-18",
            amount=Decimal("292"), counterparty_name="AJPIS", description="Alocatie",
            category=IncomeCategory.ALOCATIE, method=ClassificationMethod.PAYER_REGISTRY,
            confidence=0.99, rationale="test",
        ),
    ]
    decision, exc = compute_decision(order, txs, [], book)
    assert exc == []
    assert decision.amount_to_hold == Decimal("2000.00")
    assert decision.amount_protected == Decimal("4292.00")
