"""Agentul 6: Rezultat — decizie finală, ordin de blocare, adresa de răspuns. Proprietar: Om1 (+ Om3 pentru PDF).

Regula: dacă există excepții BLOCANTE nerezolvate -> EXCEPTION_FLAGGED (nu se blochează nimic automat).
"""
from datetime import date

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
    lines += ["", "Cu stimă,", "Departamentul Popriri și Executări Silite"]
    return "\n".join(lines)


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
    else:
        status = CaseStatus.AUTO_PROCESSED
        main = next((a for a in state.get("accounts", []) if a.account_type.value == "CURENT"), None)
        if decision and main and decision.amount_to_hold > 0:
            hold = HoldInstruction(iban=main.iban, amount=decision.amount_to_hold,
                                   reference=order.case_number or "", beneficiary_iban=order.consignment_iban)
            ctx.bank.place_hold(hold)
            decision.hold_instructions = [hold]
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
