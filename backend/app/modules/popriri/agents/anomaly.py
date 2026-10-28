"""Agentul 5: Detectarea anomaliilor și a tentativelor de eludare. Proprietar: Om1.

Reguli deterministe implementate:
  A1  Salariu reetichetat: o încasare neurmăribilă (diurnă/ajutor) de la un plătitor care
      în lunile trecute a plătit SALARIU, cu sumă apropiată, și fără salariu în fereastră.
  A2  Golire de cont: retrageri/transferuri mari după data emiterii adresei.
TODO(Om1): A3 fragmentare (salariul vine în mai multe transferuri), A4 IBAN nou de tranzit,
           + explicație generată de LLM pentru fiecare anomalie.
"""
from decimal import Decimal
from statistics import median

from app.contracts import (AgentName, AgentStatus, ExceptionCode, ExceptionFlag, IncomeCategory, Severity,
                           TxDirection)
from app.core.validators import normalize_text
from .context import AgentContext

EXEMPT = {IncomeCategory.DIURNA, IncomeCategory.AJUTOR_SOCIAL, IncomeCategory.INDEMNIZATIE_COPIL,
          IncomeCategory.ALOCATIE}
SIMILARITY = Decimal("0.15")


def run(state: dict, ctx: AgentContext) -> dict:
    emit = ctx.emit
    emit(AgentName.ANOMALY, AgentStatus.STARTED, "Caut anomalii și tentative de eludare", {})
    order, classified = state["order"], state.get("classified", [])
    history = state.get("transactions", [])
    window_ids = {c.tx_id for c in classified}
    review = state.get("review")
    overridden = {o.tx_id for o in (review.overrides if review else [])}
    exc: list[ExceptionFlag] = []

    # A1: salariu reetichetat
    for c in classified:
        if c.category not in EXEMPT or c.tx_id in overridden:
            continue
        past = [h.amount for h in history if h.counterparty_name == c.counterparty_name
                and h.tx_id not in window_ids and "SALAR" in normalize_text(h.description)]
        salary_in_window = any(x.counterparty_name == c.counterparty_name and x.category == IncomeCategory.SALARIU
                               for x in classified)
        if len(past) >= 2 and not salary_in_window:
            ref = Decimal(str(median(past)))
            if abs(c.amount - ref) <= ref * SIMILARITY:
                exc.append(ExceptionFlag(
                    code=ExceptionCode.E06_SUSPICIUNE_ELUDARE, severity=Severity.BLOCKING, agent=AgentName.ANOMALY,
                    message=(f"Posibil salariu deghizat: {c.counterparty_name} a plătit „salariu” de ~{ref} RON în "
                             f"{len(past)} luni anterioare, iar acum plătește {c.amount} RON ca „{c.description}”, "
                             "fără niciun salariu în perioada analizată."),
                    evidence=[c.tx_id]))

    # A2: golire de cont după emiterea adresei
    if order.issue_date:
        inflow = sum((c.amount for c in classified), Decimal(0))
        outflows = [h for h in history if h.direction == TxDirection.DEBIT and h.booking_date >= order.issue_date]
        out_total = sum((h.amount for h in outflows), Decimal(0))
        if inflow > 0 and out_total >= inflow * Decimal("0.5"):
            exc.append(ExceptionFlag(
                code=ExceptionCode.E06_SUSPICIUNE_ELUDARE, severity=Severity.WARNING, agent=AgentName.ANOMALY,
                message=f"După data emiterii adresei ({order.issue_date:%d.%m.%Y}) au ieșit din cont {out_total} RON "
                        f"(≥50% din sumele analizate).", evidence=[h.tx_id for h in outflows]))

    emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
         f"{len(exc)} anomalii găsite" if exc else "Nicio anomalie",
         {"exceptions": [e.code.value for e in exc]})
    return {"exceptions": exc}
