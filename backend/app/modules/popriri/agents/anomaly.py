"""Agentul 5: Detectarea anomaliilor și a tentativelor de eludare a popririi. Proprietar: Om1.

Reguli deterministe + analiză contextuală:
  A1  Salariu reetichetat (deghizat în diurnă/ajutor): o încasare neurmăribilă de la un angajator care
      în lunile trecute a plătit SALARIU, cu sumă apropiată (±15%) și fără salariu în fereastră.
  A2  Golire de cont: retrageri/transferuri mari (≥50% din intrări) imediat după data emiterii adresei.
  A3  Fragmentarea salariului (Structuring): angajatorul care plătea un salariu unic virează acum ≥2 tranșe
      mai mici (neurmăribile sau vagi) a căror sumă cumulată este apropiată de salariul istoric (±20%),
      fără salariu normal în fereastră.
  A4  Cont nou de tranzit (Pass-through): după poprire, debitorul redirecționează sume importante către
      un IBAN extern nou (neutilizat anterior în istoric).
"""
from collections import defaultdict
from decimal import Decimal
from statistics import median

from app.contracts import (AgentName, AgentStatus, ExceptionCode, ExceptionFlag, IncomeCategory, Severity,
                           TxDirection)
from app.core import llm
from app.core.validators import normalize_text
from .context import AgentContext

EXEMPT = {IncomeCategory.DIURNA, IncomeCategory.AJUTOR_SOCIAL, IncomeCategory.INDEMNIZATIE_COPIL,
          IncomeCategory.ALOCATIE}
SIMILARITY = Decimal("0.15")
FRAGMENT_SIMILARITY = Decimal("0.20")

_INVESTIGATION_SYSTEM = """Ești un investigator antifraudă și ofițer juridic în Raiffeisen Bank România.
Primești o anomalie matematică detectată în contul unui debitor supus popririi (Art. 781 și Art. 729 CPC).
Redactează o explicație scurtă (maxim 2 propoziții, în română, ton profesionist bancar) care păstrează EXACT toate cifrele și numele plătitorului și explică de ce tranzacția trebuie verificată de ofițerul HITL."""


def _past_salaries_by_employer(history: list, window_ids: set[str], payer_name: str) -> list[Decimal]:
    return [
        h.amount for h in history
        if h.counterparty_name == payer_name
        and h.tx_id not in window_ids
        and "SALAR" in normalize_text(h.description)
    ]


def run(state: dict, ctx: AgentContext) -> dict:
    emit = ctx.emit
    emit(AgentName.ANOMALY, AgentStatus.STARTED,
         "Analizez istoricul contului pentru anomalii și tentative de eludare (A1–A4)", {})
    order, classified = state["order"], state.get("classified", [])
    history = state.get("transactions", [])
    window_ids = {c.tx_id for c in classified}
    review = state.get("review")
    overridden = {o.tx_id for o in (review.overrides if review else [])}
    exc: list[ExceptionFlag] = []
    flagged_employers_a1: set[str] = set()

    # A1: Salariu reetichetat ca venit neurmăribil (ex. Diurnă în S4)
    for c in classified:
        if c.category not in EXEMPT or c.tx_id in overridden:
            continue
        past = _past_salaries_by_employer(history, window_ids, c.counterparty_name)
        salary_in_window = any(x.counterparty_name == c.counterparty_name and x.category == IncomeCategory.SALARIU
                               for x in classified)
        if len(past) >= 2 and not salary_in_window:
            ref = Decimal(str(median(past)))
            if abs(c.amount - ref) <= ref * SIMILARITY:
                flagged_employers_a1.add(c.counterparty_name)
                base_msg = (f"Posibil salariu deghizat: {c.counterparty_name} a plătit „salariu” de ~{ref} RON în "
                            f"{len(past)} luni anterioare, iar acum plătește {c.amount} RON ca „{c.description}”, "
                            "fără niciun salariu în perioada analizată.")
                llm_note = llm.chat_text(_INVESTIGATION_SYSTEM, base_msg, temperature=0.1, max_tokens=160)
                exc.append(ExceptionFlag(
                    code=ExceptionCode.E06_SUSPICIUNE_ELUDARE, severity=Severity.BLOCKING, agent=AgentName.ANOMALY,
                    message=llm_note or base_msg,
                    evidence=[c.tx_id]))
                emit(AgentName.ANOMALY, AgentStatus.PROGRESS,
                     f"Alertă A1 (Salariu deghizat): {c.counterparty_name} · {c.amount} RON („{c.description}”)",
                     {"rule": "A1", "tx_id": c.tx_id, "amount": float(c.amount), "historical_median": float(ref)})

    # A3: Fragmentarea salariului în mai multe tranșe (Structuring)
    by_payer: dict[str, list] = defaultdict(list)
    for c in classified:
        if c.category != IncomeCategory.SOLD_ANTERIOR and c.tx_id not in overridden:
            by_payer[c.counterparty_name].append(c)

    for payer_name, items in by_payer.items():
        if payer_name in flagged_employers_a1 or len(items) < 2:
            continue
        past = _past_salaries_by_employer(history, window_ids, payer_name)
        has_normal_salary = any(x.category == IncomeCategory.SALARIU for x in items)
        if len(past) >= 2 and not has_normal_salary:
            ref = Decimal(str(median(past)))
            total_fragments = sum((x.amount for x in items), Decimal(0))
            if abs(total_fragments - ref) <= ref * FRAGMENT_SIMILARITY:
                msg = (f"Suspiciune fragmentare salariu (A3): {payer_name} vira anterior un salariu unic de ~{ref} RON, "
                       f"iar în perioada analizată a efectuat {len(items)} transferuri separate însumând "
                       f"{total_fragments} RON fără etichetă salarială.")
                exc.append(ExceptionFlag(
                    code=ExceptionCode.E06_SUSPICIUNE_ELUDARE, severity=Severity.BLOCKING, agent=AgentName.ANOMALY,
                    message=msg,
                    evidence=[x.tx_id for x in items]))
                emit(AgentName.ANOMALY, AgentStatus.PROGRESS,
                     f"Alertă A3 (Fragmentare salariu): {payer_name} · {len(items)} tranșe = {total_fragments} RON",
                     {"rule": "A3", "tx_ids": [x.tx_id for x in items]})

    # A2 & A4: Golire de cont / Redirecționare către IBAN extern nou după emiterea adresei
    if order.issue_date:
        inflow = sum((c.amount for c in classified), Decimal(0))
        outflows = [h for h in history if h.direction == TxDirection.DEBIT and h.booking_date >= order.issue_date]
        out_total = sum((h.amount for h in outflows), Decimal(0))
        if inflow > 0 and out_total >= inflow * Decimal("0.5"):
            exc.append(ExceptionFlag(
                code=ExceptionCode.E06_SUSPICIUNE_ELUDARE, severity=Severity.WARNING, agent=AgentName.ANOMALY,
                message=f"După data emiterii adresei ({order.issue_date:%d.%m.%Y}) au ieșit din cont {out_total} RON "
                        f"(≥50% din sumele analizate).", evidence=[h.tx_id for h in outflows]))
            emit(AgentName.ANOMALY, AgentStatus.PROGRESS,
                 f"Alertă A2 (Golire cont după emitere): ieșiri de {out_total} RON",
                 {"rule": "A2", "outflow": float(out_total)})

        # A4: Cont nou de tranzit (IBAN destinatar care nu apare niciodată înainte de issue_date)
        prior_ibans = {
            h.counterparty_iban for h in history
            if h.direction == TxDirection.DEBIT and h.booking_date < order.issue_date and h.counterparty_iban
        }
        new_iban_outflows = [
            h for h in outflows
            if h.counterparty_iban and h.counterparty_iban not in prior_ibans and h.amount >= Decimal("1000")
        ]
        if new_iban_outflows and not any(e.severity == Severity.WARNING for e in exc):
            total_new = sum((h.amount for h in new_iban_outflows), Decimal(0))
            exc.append(ExceptionFlag(
                code=ExceptionCode.E06_SUSPICIUNE_ELUDARE, severity=Severity.WARNING, agent=AgentName.ANOMALY,
                message=f"Transfer de {total_new} RON după emiterea popririi către un IBAN extern nou "
                        f"({new_iban_outflows[0].counterparty_iban}), neutilizat în istoricul clientului (A4).",
                evidence=[h.tx_id for h in new_iban_outflows]))

    emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
         f"{len(exc)} anomalii găsite" if exc else "Nicio anomalie detectată în istoricul tranzacțiilor",
         {"exceptions": [e.code.value for e in exc]})
    return {"exceptions": exc}
