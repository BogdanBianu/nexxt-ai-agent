"""Teste unitare pentru Motorul de Reguli (Art. 729 CPC), validatoare și Core Banking mock. Proprietar: Om2.

Fiecare regulă din v2026_10.yaml are cel puțin un test (vezi numele testelor: r_exempt_01 .. r_prio_09).

Rulare:
    pytest backend/tests
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.contracts import (
    Account, ActiveGarnishment, BankSnapshot, ClassificationMethod, ClassifiedTransaction, CreditorType,
    Customer, DocType, ExceptionCode, GarnishmentOrder, IncomeCategory, IssuerType, Transaction, TxDirection,
)
from app.core.core_banking import CoreBankingMock
from app.core.validators import (check_consignment_iban, iban_bank_code, validate_amounts, validate_cnp,
                                 validate_iban, validate_issue_date)
from app.modules.popriri.engine.calculator import allocate_by_priority, compute_decision
from app.modules.popriri.engine.rules import load_rulebook

IBAN = "RO49AAAA1B31007593840000"


@pytest.fixture(scope="module")
def book():
    return load_rulebook()


def make_order(creditor=CreditorType.COMERCIAL, total_due="10000", case_number="1/2026"):
    return GarnishmentOrder(
        doc_type=DocType.POPRIRE_INFIINTARE, issuer_name="BEJ Test", issuer_type=IssuerType.EXECUTOR,
        case_number=case_number, issue_date=None, debtor_name="IONESCU MIHAI", debtor_id="1850615400011",
        creditor_name=f"Creditor {creditor.value}", creditor_type=creditor,
        principal=Decimal(total_due), enforcement_costs=Decimal("0"), total_due=Decimal(total_due),
        consignment_iban=IBAN, has_signature_and_stamp=True,
    )


def tx(tx_id, amount, category, in_window=True):
    return ClassifiedTransaction(
        tx_id=tx_id, iban=IBAN, booking_date="2026-10-15", amount=Decimal(str(amount)),
        counterparty_name="PLATITOR", description=category.value, category=category,
        method=ClassificationMethod.KEYWORD, confidence=0.95, rationale="test", in_analysis_window=in_window,
    )


def garnishment(gid, creditor, take, case_number, day=1, total_due="20000"):
    return ActiveGarnishment(
        garnishment_id=gid, customer_id="CUST-1", case_number=case_number, issuer_name="BEJ Vechi",
        creditor_name=f"Existent {creditor.value}", creditor_type=creditor, total_due=Decimal(total_due),
        monthly_periodic_take=Decimal(str(take)), registered_at=datetime(2026, 9, day, tzinfo=timezone.utc),
    )


def rule_ids(decision):
    return [r.rule_id for r in decision.rules_applied]


# ---------- validatoare ----------

def test_validators_cnp_and_iban():
    assert validate_cnp("1850615400011") is True
    assert validate_cnp("1850615400016") is False  # cifră de control greșită (vechiul CNP din schelet)
    assert validate_iban(IBAN) is True
    assert validate_iban("RO00AAAA1B31007593840000") is False


def test_consignment_iban_bank_code_and_treasury():
    assert iban_bank_code("RO49 AAAA 1B31 0075 9384 0000") == "AAAA"
    assert iban_bank_code("DE89370400440532013000") is None
    ok = check_consignment_iban(IBAN)
    assert ok.ok and ok.bank_code == "AAAA" and not ok.is_treasury
    # creanță fiscală -> trebuie cont de Trezorerie
    fiscal = check_consignment_iban(IBAN, expect_treasury=True)
    assert not fiscal.ok and "Trezoreria" in fiscal.reason
    assert not check_consignment_iban("DE89370400440532013000").ok   # IBAN valid, dar nu din RO
    assert not check_consignment_iban(None).ok


def test_issue_date_and_amount_validators():
    from datetime import date
    assert validate_issue_date(date(2026, 10, 25), received=date(2026, 10, 28))
    assert not validate_issue_date(date(2026, 11, 2), received=date(2026, 10, 28))   # emisă „în viitor”
    assert not validate_issue_date(None)
    assert validate_amounts(Decimal("14000"), Decimal("1000"), Decimal("15000"))
    assert not validate_amounts(Decimal("14000"), Decimal("1000"), Decimal("15500"))


# ---------- regulile din registru ----------

def test_rulebook_has_all_rules_with_legal_source(book):
    expected = {"R-EXEMPT-01", "R-SPECIAL-02", "R-WAGE-03", "R-WAGE-04", "R-CONC-05", "R-MIN-06",
                "R-OTHER-07", "R-CAP-08", "R-PRIO-09", "R-DUP-10"}
    assert expected <= set(book.rules)
    assert all(r.legal_source for r in book.rules.values())
    assert all(book.rule(i).legal_source.startswith("CPC") for i in expected - {"R-DUP-10"})
    assert book.creditor_priority == [CreditorType.INTRETINERE, CreditorType.FISCAL, CreditorType.COMERCIAL]


def test_s1_protects_alocatie_and_diurna_takes_third_of_salary_and_all_other(book):
    """S1: R-EXEMPT-01 + R-WAGE-04 + R-OTHER-07 -> 2.000 + 800 + 3.000 = 5.800 RON."""
    txs = [tx("T1", 6000, IncomeCategory.SALARIU), tx("T2", 292, IncomeCategory.ALOCATIE),
           tx("T3", 1500, IncomeCategory.DIURNA), tx("T4", 800, IncomeCategory.ALT_VENIT),
           tx("T5", 3000, IncomeCategory.SOLD_ANTERIOR)]
    decision, exc = compute_decision(make_order(total_due="15000"), txs, [], book)
    assert exc == []
    assert decision.amount_to_hold == Decimal("5800.00")
    assert decision.amount_protected == Decimal("5792.00")
    assert {"R-EXEMPT-01", "R-WAGE-04", "R-OTHER-07"} <= set(rule_ids(decision))


def test_r_exempt_01_only_protected_income_holds_nothing(book):
    """S2: indemnizație creștere copil + alocație -> 0 RON blocați."""
    txs = [tx("T1", 3500, IncomeCategory.INDEMNIZATIE_COPIL), tx("T2", 719, IncomeCategory.ALOCATIE),
           tx("T3", 400, IncomeCategory.AJUTOR_SOCIAL)]
    decision, exc = compute_decision(make_order(total_due="5000"), txs, [], book)
    assert exc == []
    assert decision.amount_to_hold == Decimal("0.00")
    assert decision.exempt_total == Decimal("4619.00")


def test_r_special_02_sick_leave_protected_for_commercial_creditor(book):
    decision, _ = compute_decision(make_order(), [tx("T1", 3000, IncomeCategory.INDEMNIZATIE_BOALA)], [], book)
    assert decision.amount_to_hold == Decimal("0.00")
    assert "R-SPECIAL-02" in rule_ids(decision)


def test_r_special_02_sick_leave_seizable_half_for_child_support(book):
    order = make_order(creditor=CreditorType.INTRETINERE)
    decision, _ = compute_decision(order, [tx("T1", 3000, IncomeCategory.INDEMNIZATIE_BOALA)], [], book)
    assert decision.amount_to_hold == Decimal("1500.00")


def test_r_wage_03_child_support_takes_half_of_salary(book):
    order = make_order(creditor=CreditorType.INTRETINERE)
    decision, _ = compute_decision(order, [tx("T1", 6000, IncomeCategory.SALARIU)], [], book)
    assert decision.amount_to_hold == Decimal("3000.00")
    assert "R-WAGE-03" in rule_ids(decision)


def test_r_wage_04_fiscal_creditor_takes_third_of_pension(book):
    order = make_order(creditor=CreditorType.FISCAL)
    decision, _ = compute_decision(order, [tx("T1", 4500, IncomeCategory.PENSIE)], [], book)
    assert decision.amount_to_hold == Decimal("1500.00")
    assert "R-WAGE-04" in rule_ids(decision)


def test_r_min_06_income_below_minimum_wage(book):
    """2.000 RON < 2.574 RON: se urmărește 1/3 doar din ce depășește 1.287 RON -> 237,67 RON."""
    decision, _ = compute_decision(make_order(), [tx("T1", 2000, IncomeCategory.PENSIE)], [], book)
    assert decision.amount_to_hold == Decimal("237.67")
    assert "R-MIN-06" in rule_ids(decision)


def test_r_other_07_other_income_and_previous_balance_fully_seizable(book):
    txs = [tx("T1", 1200, IncomeCategory.ALT_VENIT), tx("T2", 2500, IncomeCategory.SOLD_ANTERIOR)]
    decision, _ = compute_decision(make_order(), txs, [], book)
    assert decision.amount_to_hold == Decimal("3700.00")
    assert decision.seizable_other == Decimal("3700.00")


def test_r_cap_08_hold_never_exceeds_total_due(book):
    txs = [tx("T1", 6000, IncomeCategory.SALARIU), tx("T2", 5000, IncomeCategory.SOLD_ANTERIOR)]
    decision, _ = compute_decision(make_order(total_due="1250"), txs, [], book)
    assert decision.amount_to_hold == Decimal("1250.00")
    assert "R-CAP-08" in rule_ids(decision)


def test_transactions_outside_analysis_window_are_ignored(book):
    txs = [tx("T1", 6000, IncomeCategory.SALARIU), tx("T0", 6000, IncomeCategory.SALARIU, in_window=False)]
    decision, _ = compute_decision(make_order(), txs, [], book)
    assert decision.periodic_income == Decimal("6000")
    assert decision.amount_to_hold == Decimal("2000.00")


def test_r_conc_05_and_r_prio_09_child_support_over_commercial(book):
    """S3: deja se rețin 2.000 RON (comercial); plafonul 1/2 lasă 1.000 RON -> E04.
    R-PRIO-09 propune ca întreținerea să ia tot plafonul (3.000 RON) înaintea creditorului comercial."""
    active = [garnishment("G-1", CreditorType.COMERCIAL, 2000, "500/2026")]
    order = make_order(creditor=CreditorType.INTRETINERE, total_due="12000", case_number="777/2026")
    decision, exc = compute_decision(order, [tx("T1", 6000, IncomeCategory.SALARIU)], active, book)

    assert decision.amount_to_hold == Decimal("1000.00")
    assert [e.code for e in exc] == [ExceptionCode.E04_POPRIRI_CONCURENTE]
    assert {"R-CONC-05", "R-PRIO-09"} <= set(rule_ids(decision))
    alloc = {a.case_number: a.amount for a in decision.allocations}
    assert alloc == {"777/2026": Decimal("3000.00"), "500/2026": Decimal("0.00")}
    assert decision.allocations[0].creditor_type == CreditorType.INTRETINERE


def test_r_prio_09_same_rank_new_order_waits_behind_existing(book):
    active = [garnishment("G-1", CreditorType.COMERCIAL, 1000, "500/2026")]
    decision, exc = compute_decision(make_order(case_number="900/2026"),
                                     [tx("T1", 6000, IncomeCategory.SALARIU)], active, book)
    assert exc == []                                  # încape sub plafonul de 3.000 RON
    assert decision.amount_to_hold == Decimal("2000.00")
    alloc = {a.case_number: a.amount for a in decision.allocations}
    assert alloc == {"500/2026": Decimal("1000.00"), "900/2026": Decimal("2000.00")}


def test_allocate_by_priority_order_and_ceilings(book):
    claims = [
        {"key": "com", "creditor_type": CreditorType.COMERCIAL, "ceiling": Decimal("5000"), "order": 0},
        {"key": "fisc", "creditor_type": CreditorType.FISCAL, "ceiling": Decimal("1500"), "order": 1},
        {"key": "intr", "creditor_type": CreditorType.INTRETINERE, "ceiling": Decimal("1000"), "order": 2},
    ]
    shares = allocate_by_priority(Decimal("3000"), claims, book)
    assert shares == {"intr": Decimal("1000.00"), "fisc": Decimal("1500.00"), "com": Decimal("500.00")}


# ---------- Core Banking mock ----------

def test_core_banking_converts_eur_account_to_ron():
    snap = BankSnapshot(
        customers=[Customer(customer_id="C1", full_name="IONESCU MIHAI", national_id="1850615400011")],
        accounts=[Account(iban=IBAN, customer_id="C1", current_balance=Decimal("100")),
                  Account(iban="RO09BCYP0000001234567890", customer_id="C1", currency="EUR",
                          current_balance=Decimal("1000"))],
        transactions=[Transaction(tx_id="E1", iban="RO09BCYP0000001234567890", booking_date="2026-10-10",
                                  direction=TxDirection.CREDIT, amount=Decimal("1000"),
                                  counterparty_name="X", description="Transfer")],
    )
    bank = CoreBankingMock(snap)
    [t] = bank.get_transactions("C1")
    assert t.amount == Decimal("4975.00") and "EUR" in t.description
    assert bank.balance_in_ron("C1") == Decimal("5075.00")
