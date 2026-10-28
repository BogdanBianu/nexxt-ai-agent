"""Starea grafului LangGraph pentru modulele juridice LexOps. Proprietar: Om1.

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
    doc_type_hint: DocType                 # tipul stabilit de Intake Router (LangGraph ignoră cheile nedeclarate)
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
    skip_reason: str                       # motiv opțional pentru evenimentul SKIPPED pe agenții 3-5
    aml_flags: list[ExceptionFlag]         # alerte AML specifice modulului autoritati
    gdpr_right: str                        # dreptul invocat în modulul gdpr (ACCES/STERGERE/OPOZITIE/ANSPDCP)


# Câmpuri cu reducer (pentru runner-ul secvențial de rezervă)
ADDITIVE_KEYS = {"exceptions"}


def merge(state: dict[str, Any], update: dict[str, Any] | None) -> dict[str, Any]:
    for k, v in (update or {}).items():
        state[k] = (state.get(k) or []) + list(v) if k in ADDITIVE_KEYS else v
    return state
