"""Agentul 6: Rezultat — decizie finală, ordin de blocare, adresa de răspuns. Proprietar: Om1 (+ Om3 pentru PDF).

Regula: dacă există excepții BLOCANTE nerezolvate -> EXCEPTION_FLAGGED (nu se blochează nimic automat).
"""
from datetime import date
from decimal import Decimal

from app.contracts import (AgentName, AgentStatus, CaseOutcome, CaseStatus, DocType, HoldInstruction,
                           Severity)
from app.core import llm
from .context import AgentContext


def response_letter(state: dict) -> str:
    """Textul adresei de răspuns către executor. TODO(Om3): șablon HTML -> PDF oficial."""
    o, d, cust = state["order"], state.get("decision"), state.get("customer")
    lines = [
        "RAIFFEISEN BANK S.A. — Departamentul Popriri",
        f"Data: {date.today():%d.%m.%Y}",
        f"Către: {o.issuer_name}",
        f"Ref.: dosar de executare nr. {o.case_number or o.references_case_number}",
        "",
    ]
    if o.doc_type == DocType.POPRIRE_SISTARE:
        lines.append(f"Vă confirmăm sistarea popririi înființate asupra conturilor debitorului "
                     f"{o.debtor_name} și ridicarea indisponibilizării.")
    elif d:
        lines += [
            f"Urmare a adresei de înființare a popririi privind debitorul {o.debtor_name} (CNP/CUI {o.debtor_id}), "
            f"vă comunicăm că am procedat la indisponibilizarea sumei de {d.amount_to_hold} RON, "
            f"din totalul de {o.total_due} RON.",
            f"Suma de {d.exempt_total} RON nu a fost indisponibilizată, fiind protejată conform art. 729 CPC "
            "(venituri neurmăribile sau peste cota legală).",
            f"Sumele vor fi virate în contul de consemnare {o.consignment_iban}.",
        ]
    elif not cust:
        lines.append(f"Vă comunicăm că debitorul {o.debtor_name} (CNP/CUI {o.debtor_id}) nu figurează în evidențele "
                     "Raiffeisen Bank S.A. cu conturi deschise; nu s-a indisponibilizat nicio sumă.")
    lines += ["", "Cu stimă,", "Departamentul Popriri și Executări Silite"]
    return "\n".join(lines)


def hold_instructions(accounts: list, amount: Decimal, order) -> list[HoldInstruction]:
    """Împarte suma de blocat pe conturi: întâi contul CURENT, apoi celelalte după sold.

    Fiecare cont primește cel mult soldul lui; restul (dacă soldurile nu ajung) rămâne pe primul cont,
    ca suma din ordine să fie mereu egală cu `amount_to_hold`.
    """
    ordered = sorted(accounts, key=lambda a: (a.account_type.value != "CURENT", -a.current_balance))
    holds, left = [], amount
    for acc in ordered:
        take = min(max(acc.current_balance, Decimal(0)), left)
        if take > 0:
            holds.append(HoldInstruction(iban=acc.iban, amount=take, reference=order.case_number or "",
                                         beneficiary_iban=order.consignment_iban))
            left -= take
    if left > 0 and ordered:
        if holds:
            holds[0] = holds[0].model_copy(update={"amount": holds[0].amount + left})
        else:
            holds.append(HoldInstruction(iban=ordered[0].iban, amount=left, reference=order.case_number or "",
                                         beneficiary_iban=order.consignment_iban))
    return holds


def run(state: dict, ctx: AgentContext) -> dict:
    emit = ctx.emit
    emit(AgentName.OUTCOME, AgentStatus.STARTED, "Stabilesc rezultatul dosarului", {})
    order, decision = state["order"], state.get("decision")
    review = state.get("review")
    resolved = set(review.resolve_codes) if review else set()
    blocking = [e for e in state.get("exceptions", [])
                if e.severity == Severity.BLOCKING and not e.resolved and e.code.value not in resolved]

    if blocking:
        status = CaseStatus.EXCEPTION_FLAGGED
        summary = (f"Dosarul necesită verificare umană: {len(blocking)} excepții blocante "
                   f"({', '.join(sorted({e.code.value for e in blocking}))}). Nu s-a blocat automat nicio sumă.")
        letter = None
    elif order.doc_type == DocType.POPRIRE_SISTARE:
        status, summary, letter = CaseStatus.LIFTED, "Poprirea a fost sistată, indisponibilizarea se ridică.", response_letter(state)
    elif decision is None:
        # ofițerul a lămurit excepția de identitate/duplicat, dar nu există calcul (ex. debitorul nu e client)
        status = CaseStatus.AUTO_PROCESSED
        summary = ("Excepțiile au fost lămurite de ofițer; nu există conturi de poprit, "
                   "nu s-a indisponibilizat nicio sumă.")
        letter = response_letter(state)
    else:
        status = CaseStatus.AUTO_PROCESSED
        if decision.amount_to_hold > 0:
            decision.hold_instructions = hold_instructions(state.get("accounts", []), decision.amount_to_hold, order)
            for hold in decision.hold_instructions:
                ctx.bank.place_hold(hold)
        summary = (f"Poprire procesată automat: se indisponibilizează {decision.amount_to_hold} RON din "
                   f"{order.total_due} RON datorați; {decision.amount_protected} RON rămân clientului.")
        letter = response_letter(state)

    # opțional: LLM-ul reformulează rezumatul pentru ofițer (fallback = textul de mai sus)
    polished = llm.chat_text("Reformulează concis, profesionist, în română, pentru un ofițer bancar. "
                             "Nu schimba nicio cifră.", summary, max_tokens=200)
    outcome = CaseOutcome(status=status, summary=polished or summary, response_letter_text=letter)
    emit(AgentName.OUTCOME, AgentStatus.COMPLETED, f"Rezultat: {status.value}",
         {"status": status.value, "summary": outcome.summary})
    return {"outcome": outcome, "decision": decision}
