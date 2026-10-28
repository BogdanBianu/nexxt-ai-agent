"""Dosarul (Case) = obiectul central pe care îl vede frontend-ul."""
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .banking import Account, ActiveGarnishment, Customer
from .common import Contract
from .decision import CaseOutcome, ClassifiedTransaction, ExceptionFlag, GarnishmentDecision
from .documents import GarnishmentOrder, IncomingDocument
from .enums import AgentName, AgentStatus, CaseStatus, DocType, IncomeCategory


class AgentEvent(Contract):
    """Un eveniment emis de un agent. Frontend-ul le primește live (SSE) pentru animație."""
    case_id: str
    seq: int
    timestamp: datetime
    agent: AgentName
    status: AgentStatus
    message: str                                # în română, scurt, afișabil
    data: dict[str, Any] = Field(default_factory=dict)


class TxOverride(Contract):
    """Ofițerul reclasifică manual o tranzacție (Workbench HITL)."""
    tx_id: str
    category: IncomeCategory
    note: str | None = None


class ReviewAction(Contract):
    reviewer: str
    overrides: list[TxOverride] = Field(default_factory=list)
    resolve_codes: list[str] = Field(default_factory=list)   # ex. ["E06"] -> marcate rezolvate
    note: str | None = None
    timestamp: datetime | None = None


class LlmUsage(Contract):
    """Telemetria AI a unui dosar, adunată peste toate rulările (inclusiv re-rulările HITL)."""
    calls: int = 0                              # apeluri Bedrock facturate
    cache_hits: int = 0                         # răspunsuri servite din cache-ul pe disc (cost 0)
    failed_calls: int = 0                       # eșecuri -> fallback determinist
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0                         # timpul total petrecut în LLM
    cost_usd: float = 0.0
    cost_eur: float = 0.0
    cache_savings_usd: float = 0.0              # cât ar fi costat apelurile servite din cache
    models: list[str] = Field(default_factory=list)


class ApprovalAction(Contract):
    """Corpul `POST /api/cases/{id}/approve` și `/reject`: angajatul are ultimul cuvânt."""
    reviewer: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)   # obligatorie la respingere


class ApprovalRecord(Contract):
    """Decizia finală a angajatului asupra propunerii agentului."""
    decision: Literal["APPROVED", "REJECTED"]
    reviewer: str
    note: str | None = None
    timestamp: datetime
    previous_status: CaseStatus                 # PENDING_APPROVAL sau EXCEPTION_FLAGGED


class AuditEntry(Contract):
    timestamp: datetime
    actor: str                                  # numele agentului sau "user:<nume>"
    action: str
    details: dict[str, Any] = Field(default_factory=dict)


class Case(Contract):
    case_id: str
    module_id: str | None = None                # "popriri" | "autoritati" | ...
    scenario_id: str | None = None
    status: CaseStatus = CaseStatus.RECEIVED
    proposed_status: CaseStatus | None = None   # verdictul agentului (AUTO_PROCESSED / LIFTED) până la aprobare
    approval: ApprovalRecord | None = None      # aprobarea / respingerea angajatului
    doc_type: DocType = DocType.NECUNOSCUT
    created_at: datetime
    updated_at: datetime

    document: IncomingDocument
    order: GarnishmentOrder | None = None
    customer: Customer | None = None
    accounts: list[Account] = Field(default_factory=list)
    active_garnishments: list[ActiveGarnishment] = Field(default_factory=list)
    classified_transactions: list[ClassifiedTransaction] = Field(default_factory=list)
    decision: GarnishmentDecision | None = None
    exceptions: list[ExceptionFlag] = Field(default_factory=list)
    outcome: CaseOutcome | None = None

    reviews: list[ReviewAction] = Field(default_factory=list)
    audit: list[AuditEntry] = Field(default_factory=list)
    llm_usage: LlmUsage = Field(default_factory=LlmUsage)
