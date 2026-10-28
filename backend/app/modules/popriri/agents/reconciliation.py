"""Agentul 2: Identificare client și reconciliere cu evidențele băncii. Proprietar: Om1 (logică) / Om2 (unelte).

Verifică: clientul există, numele corespunde, statutul clientului, dosar duplicat,
sistare pentru o poprire existentă. Încarcă conturile, tranzacțiile și popririle active.
"""
from app.contracts import (AgentName, AgentStatus, CustomerStatus, DocType, ExceptionCode, ExceptionFlag,
                           Severity)
from app.core.validators import names_match
from .context import AgentContext

IDENTITY_CODES = {ExceptionCode.E01_IDENTITATE, ExceptionCode.E02_DUPLICAT,
                  ExceptionCode.E07_SISTARE_FARA_POPRIRE, ExceptionCode.E08_STATUT_CLIENT}


def run(state: dict, ctx: AgentContext) -> dict:
    emit, order = ctx.emit, state["order"]
    emit(AgentName.RECONCILIATION, AgentStatus.STARTED, "Caut debitorul în Core Banking", {})
    exc: list[ExceptionFlag] = []
    review = state.get("review")
    resolved = set(review.resolve_codes) if review else set()   # excepții pe care ofițerul le-a lămurit

    # dacă extragerea a găsit deja un CNP invalid (și ofițerul nu l-a lămurit), nu mai căutăm
    if any(e.code == ExceptionCode.E01_IDENTITATE and e.severity == Severity.BLOCKING
           and e.code.value not in resolved for e in state.get("exceptions", [])):
        emit(AgentName.RECONCILIATION, AgentStatus.SKIPPED, "CNP invalid: identificarea nu e posibilă", {})
        return {"stop_after_reconciliation": True}

    customer = ctx.bank.find_customer(order.debtor_id) if order.debtor_id else None
    if customer is None:
        exc.append(ExceptionFlag(code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING,
                                 agent=AgentName.RECONCILIATION,
                                 message=f"Niciun client cu CNP/CUI {order.debtor_id}. "
                                         "Se pregătește răspuns „debitorul nu are conturi”, după verificare.",
                                 evidence=["debtor_id"]))
        emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED, "Client negăsit", {})
        return {"customer": None, "exceptions": exc, "stop_after_reconciliation": True}

    if not names_match(customer.full_name, order.debtor_name):
        exc.append(ExceptionFlag(code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING,
                                 agent=AgentName.RECONCILIATION,
                                 message=f"Numele din adresă ({order.debtor_name}) nu corespunde titularului "
                                         f"CNP-ului din bancă ({customer.full_name}).",
                                 evidence=["debtor_name"]))
    if customer.status != CustomerStatus.ACTIV:
        exc.append(ExceptionFlag(code=ExceptionCode.E08_STATUT_CLIENT, severity=Severity.BLOCKING,
                                 agent=AgentName.RECONCILIATION,
                                 message=f"Clientul are statutul {customer.status.value}.", evidence=[customer.customer_id]))

    accounts = ctx.bank.get_accounts(customer.customer_id)
    transactions = ctx.bank.get_transactions(customer.customer_id)
    active = ctx.bank.get_active_garnishments(customer.customer_id)

    if order.doc_type == DocType.POPRIRE_INFIINTARE and order.case_number:
        dup = next((g for g in active if g.case_number == order.case_number), None)
        if dup:
            exc.append(ExceptionFlag(code=ExceptionCode.E02_DUPLICAT, severity=Severity.BLOCKING,
                                     agent=AgentName.RECONCILIATION,
                                     message=f"Dosarul de executare {order.case_number} este deja înregistrat "
                                             f"(poprirea {dup.garnishment_id} din {dup.registered_at:%d.%m.%Y}).",
                                     evidence=[dup.garnishment_id]))
        active = [g for g in active if g.case_number != order.case_number]

    if order.doc_type == DocType.POPRIRE_SISTARE:
        target = order.references_case_number or order.case_number
        if not any(g.case_number == target for g in active):
            exc.append(ExceptionFlag(code=ExceptionCode.E07_SISTARE_FARA_POPRIRE, severity=Severity.BLOCKING,
                                     agent=AgentName.RECONCILIATION,
                                     message=f"Se cere sistarea popririi din dosarul {target}, dar nu există "
                                             "o poprire activă înregistrată.", evidence=[str(target)]))

    stop = any(e.code in IDENTITY_CODES and e.severity == Severity.BLOCKING and e.code.value not in resolved
               for e in exc)
    emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED,
         f"Client {customer.full_name}: {len(accounts)} conturi, {len(active)} popriri active",
         {"customer_id": customer.customer_id, "accounts": len(accounts), "active_garnishments": len(active),
          "exceptions": [e.code.value for e in exc]})
    return {"customer": customer, "accounts": accounts, "transactions": transactions,
            "active_garnishments": active, "exceptions": exc, "stop_after_reconciliation": stop}
