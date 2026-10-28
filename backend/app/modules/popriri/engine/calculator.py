"""Motorul de calcul DETERMINIST pentru popriri. Proprietar: Om2.

Aici NU se folosește LLM. Intrări: adresa (GarnishmentOrder), încasările clasificate,
popririle deja active. Ieșire: GarnishmentDecision + eventuale excepții (E04).
Orice modificare -> rulați `pytest backend/tests/test_calculator.py`.
"""
from decimal import Decimal

from app.contracts import (ActiveGarnishment, AgentName, ClassifiedTransaction, CreditorAllocation,
                           CreditorType, ExceptionCode, ExceptionFlag, GarnishmentDecision,
                           GarnishmentOrder, RuleApplication, Severity, money)
from .rules import RuleBook

ZERO = Decimal("0")


def compute_decision(order: GarnishmentOrder, txs: list[ClassifiedTransaction],
                     active: list[ActiveGarnishment], book: RuleBook
                     ) -> tuple[GarnishmentDecision, list[ExceptionFlag]]:
    creditor = order.creditor_type
    window = [t for t in txs if t.in_analysis_window]
    applied: list[RuleApplication] = []
    exceptions: list[ExceptionFlag] = []

    exempt_total = ZERO
    seizable_other = ZERO
    periodic_txs: list[ClassifiedTransaction] = []

    # 1. Fiecare încasare trece prin regula categoriei ei
    by_rule: dict[str, list[ClassifiedTransaction]] = {}
    for t in window:
        if t.category in book.periodic_categories:
            periodic_txs.append(t)
            continue
        rule = book.rule_for(t.category, creditor)
        if rule is None:
            # categorie fără regulă = tratăm prudent ca neurmăribilă și semnalăm
            exempt_total += t.amount
            continue
        by_rule.setdefault(rule.id, []).append(t)

    for rule_id, items in by_rule.items():
        rule = book.rule(rule_id)
        quota = book.quota(rule, creditor)
        base = sum((t.amount for t in items), ZERO)
        seizable = money(base * quota)
        exempt_total += base - seizable
        seizable_other += seizable
        applied.append(RuleApplication(rule_id=rule.id, legal_source=rule.legal_source,
                                       description=rule.description, base_amount=base,
                                       seizable_amount=seizable, tx_ids=[t.tx_id for t in items]))

    # 2. Venitul periodic (salariu/pensie): cotă + protecția salariului minim + plafon cumulat
    periodic = sum((t.amount for t in periodic_txs), ZERO)
    seizable_periodic = ZERO
    if periodic > 0:
        wage_rule = book.rule_for(periodic_txs[0].category, creditor)
        quota = book.quota(wage_rule, creditor)
        seizable_periodic = money(periodic * quota)
        applied.append(RuleApplication(rule_id=wage_rule.id, legal_source=wage_rule.legal_source,
                                       description=wage_rule.description, base_amount=periodic,
                                       seizable_amount=seizable_periodic,
                                       tx_ids=[t.tx_id for t in periodic_txs]))

        # R-MIN-06: venit sub salariul minim net
        if book.salariu_minim_net and periodic < book.salariu_minim_net:
            protected_floor = book.salariu_minim_net / 2
            limited = money(max(periodic - protected_floor, ZERO) * quota)
            if limited < seizable_periodic:
                r = book.rule("R-MIN-06")
                applied.append(RuleApplication(rule_id=r.id, legal_source=r.legal_source,
                                               description=r.description, base_amount=periodic,
                                               seizable_amount=limited))
                seizable_periodic = limited

        # R-CONC-05: plafon cumulat cu popririle deja active
        if active:
            already = sum((g.monthly_periodic_take for g in active), ZERO)
            room = max(money(periodic * book.cumulative_cap) - already, ZERO)
            r = book.rule("R-CONC-05")
            if room < seizable_periodic:
                applied.append(RuleApplication(rule_id=r.id, legal_source=r.legal_source,
                                               description=r.description, base_amount=periodic,
                                               seizable_amount=room))
                seizable_periodic = room
                has_priority = creditor == CreditorType.INTRETINERE and any(
                    g.creditor_type != CreditorType.INTRETINERE for g in active)
                exceptions.append(ExceptionFlag(
                    code=ExceptionCode.E04_POPRIRI_CONCURENTE, severity=Severity.BLOCKING,
                    agent=AgentName.RULE_ENGINE,
                    message=(f"Plafonul de 1/2 din venitul periodic este atins: deja se rețin "
                             f"{already} RON/lună din {periodic} RON. Rămân {room} RON pentru noua poprire. "
                             + ("Noul creditor (întreținere) are prioritate față de popririle existente: "
                                "trebuie reîmpărțite reținerile." if has_priority else
                                "Verificați ordinea de preferință a creditorilor.")),
                    evidence=[g.case_number for g in active]))

    # 3. Plafonare la datorie (R-CAP-08)
    seizable_total = seizable_periodic + seizable_other
    to_hold = min(seizable_total, order.total_due)
    if to_hold < seizable_total:
        r = book.rule("R-CAP-08")
        applied.append(RuleApplication(rule_id=r.id, legal_source=r.legal_source, description=r.description,
                                       base_amount=seizable_total, seizable_amount=to_hold))

    exempt_total += periodic - seizable_periodic
    total_window = sum((t.amount for t in window), ZERO)
    decision = GarnishmentDecision(
        periodic_income=periodic, seizable_periodic=seizable_periodic, seizable_other=seizable_other,
        exempt_total=money(exempt_total), amount_to_hold=money(to_hold),
        amount_protected=money(total_window - to_hold), total_due=order.total_due,
        rules_applied=applied,
        allocations=[CreditorAllocation(case_number=order.case_number or "?",
                                        creditor_name=order.creditor_name or "?",
                                        creditor_type=creditor, amount=money(to_hold))],
        rules_version=book.version,
    )
    return decision, exceptions
