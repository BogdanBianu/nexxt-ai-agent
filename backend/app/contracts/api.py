"""Corpurile cererilor și răspunsurilor HTTP care nu sunt deja în alte contracte."""
from typing import Any

from pydantic import Field

from .common import Contract
from .enums import CaseStatus, CreditorType, DocType, IncomeCategory, ModuleStatus


class ModuleInfo(Contract):
    module_id: str
    name: str
    description: str
    status: ModuleStatus
    handled_doc_types: list[DocType] = Field(default_factory=list)


class ScenarioInfo(Contract):
    scenario_id: str
    title: str
    description: str


class CreateCaseFromScenario(Contract):
    scenario_id: str


class CaseSummary(Contract):
    """Rând în Inbox-ul juridic."""
    case_id: str
    scenario_id: str | None
    module_id: str | None
    doc_type: DocType
    status: CaseStatus
    debtor_name: str | None
    case_number: str | None
    amount_to_hold: float | None
    open_exceptions: int
    created_at: str


class RuleInfo(Contract):
    """O regulă din registrul YAML, pentru afișare în UI."""
    id: str
    legal_source: str
    description: str
    categories: list[IncomeCategory] = Field(default_factory=list)
    creditor_types: list[CreditorType] = Field(default_factory=list)
    quota: float | None = None
    quota_if_creditor: dict[CreditorType, float] = Field(default_factory=dict)


class RuleBookInfo(Contract):
    """Răspunsul `GET /api/rules`."""
    version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    periodic_categories: list[IncomeCategory] = Field(default_factory=list)
    rules: list[RuleInfo] = Field(default_factory=list)


class PlatformMetrics(Contract):
    """Răspunsul `GET /api/metrics` (KPI-uri pentru dashboard și pitch)."""
    total_cases: int
    cases_by_status: dict[str, int] = Field(default_factory=dict)
    automation_rate: float                      # % dosare popriri finalizate fără om (AUTO_PROCESSED + LIFTED)
    avg_processing_ms: float                    # timpul mediu de rulare a pipeline-ului de agenți
    total_amount_held: float                    # RON indisponibilizați
    total_amount_protected: float               # RON lăsați clientului (protejați de lege)
    total_exempt: float                         # RON neurmăribili conform art. 729 CPC
    exceptions_by_code: dict[str, int] = Field(default_factory=dict)
    reviews_count: int = 0                      # intervenții HITL
