"""Formatul unui scenariu sintetic (data/scenarios/*.json). Proprietar: Om3."""
from decimal import Decimal

from pydantic import Field

from .banking import BankSnapshot
from .common import Contract, Money
from .documents import IncomingDocument
from .enums import CaseStatus, DocType


class ExpectedOutcome(Contract):
    """Rezultatul corect („ground truth”). Folosit de scripts/run_scenarios.py (Om5)."""
    doc_type: DocType
    status: CaseStatus
    amount_to_hold: Money = Decimal("0")
    exception_codes: list[str] = Field(default_factory=list)
    # după ce ofițerul aplică override-urile din `review` (opțional, pentru demo HITL)
    amount_after_review: Money | None = None


class Scenario(Contract):
    scenario_id: str                            # "S1"
    title: str
    description: str
    document: IncomingDocument
    bank: BankSnapshot
    expected: ExpectedOutcome
    demo_review: dict | None = None             # un ReviewAction de aplicat în demo
