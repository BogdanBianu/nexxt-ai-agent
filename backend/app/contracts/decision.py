"""Rezultatele agenților: clasificări, reguli aplicate, excepții, decizia finală."""
from datetime import date

from pydantic import Field

from .banking import HoldInstruction
from .common import Contract, Money
from .enums import (AgentName, CaseStatus, ClassificationMethod, CreditorType, ExceptionCode,
                    IncomeCategory, Severity)


class ClassifiedTransaction(Contract):
    """O încasare + natura ei juridică (output Agent INCOME_CLASSIFIER)."""
    tx_id: str
    iban: str
    booking_date: date
    amount: Money
    counterparty_name: str
    description: str
    category: IncomeCategory
    method: ClassificationMethod
    confidence: float = Field(ge=0, le=1)
    rationale: str                              # explicație în română, afișată în UI
    in_analysis_window: bool = True             # intră în calculul popririi?


class RuleApplication(Contract):
    """O regulă din registru aplicată efectiv (output Agent RULE_ENGINE)."""
    rule_id: str                                # "R-WAGE-04"
    legal_source: str                           # "CPC art. 729 alin. (1) lit. b)"
    description: str
    base_amount: Money                          # suma pe care s-a aplicat
    seizable_amount: Money                      # cât rezultă urmăribil
    tx_ids: list[str] = Field(default_factory=list)


class ExceptionFlag(Contract):
    code: ExceptionCode
    severity: Severity
    agent: AgentName
    message: str                                # mesaj pentru ofițer, în română
    evidence: list[str] = Field(default_factory=list)   # tx_id-uri, câmpuri, citate din document
    resolved: bool = False
    resolution_note: str | None = None


class CreditorAllocation(Contract):
    case_number: str
    creditor_name: str
    creditor_type: CreditorType
    amount: Money


class GarnishmentDecision(Contract):
    """Calculul final (output Agent RULE_ENGINE, completat de OUTCOME)."""
    periodic_income: Money = 0                  # salariu + pensie în fereastră
    seizable_periodic: Money = 0                # partea urmăribilă din venitul periodic
    seizable_other: Money = 0                   # alte venituri + sold anterior
    exempt_total: Money = 0                     # sume neurmăribile (protejate de lege)
    amount_to_hold: Money = 0                   # CÂT SE BLOCHEAZĂ
    amount_protected: Money = 0                 # cât rămâne liber clientului
    total_due: Money = 0
    rules_applied: list[RuleApplication] = Field(default_factory=list)
    allocations: list[CreditorAllocation] = Field(default_factory=list)
    hold_instructions: list[HoldInstruction] = Field(default_factory=list)
    rules_version: str = ""


class CaseOutcome(Contract):
    """Ce produce Agentul OUTCOME la final."""
    status: CaseStatus
    summary: str                                # 2-3 fraze pentru ofițer
    response_letter_text: str | None = None     # adresa de răspuns către executor
    response_letter_pdf: str | None = None      # cale relativă (Om3 generează PDF-ul)
