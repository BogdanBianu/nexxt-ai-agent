"""Starea grafului LangGraph pentru modulul de popriri. Proprietar: Om1.

Fiecare agent primește starea și întoarce DOAR câmpurile pe care le modifică.
`exceptions` se ADUNĂ (reducer operator.add): fiecare agent își adaugă excepțiile.
"""
import operator
from typing import Annotated, Any, TypedDict

from app.contracts import (Account, ActiveGarnishment, CaseOutcome, ClassifiedTransaction, Customer,
                           DocType, ExceptionFlag, GarnishmentDecision, GarnishmentOrder, IncomingDocument,
                           ReviewAction, Transaction)


class PopririState(TypedDict, total=False):
    case_id: str
    document: IncomingDocument
    doc_type_hint: DocType | None
    review: ReviewAction | None            # override-uri de la ofițer (re-rulare după HITL)

    order: GarnishmentOrder | None
    customer: Customer | None
    accounts: list[Account]
    transactions: list[Transaction]        # tot istoricul (pentru anomalii)
    active_garnishments: list[ActiveGarnishment]
    classified: list[ClassifiedTransaction]
    decision: GarnishmentDecision | None
    outcome: CaseOutcome | None
    exceptions: Annotated[list[ExceptionFlag], operator.add]
    stop_after_reconciliation: bool        # erori de identitate -> direct la OUTCOME


# Câmpuri cu reducer (pentru runner-ul secvențial de rezervă)
ADDITIVE_KEYS = {"exceptions"}


def merge(state: dict[str, Any], update: dict[str, Any] | None) -> dict[str, Any]:
    for k, v in (update or {}).items():
        state[k] = (state.get(k) or []) + list(v) if k in ADDITIVE_KEYS else v
    return state
