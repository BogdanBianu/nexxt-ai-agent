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


class AiTelemetry(Contract):
    """Costul AI vs. costul muncii manuale (blocul `ai` din `GET /api/metrics`, dashboard-ul Executive Impact)."""
    llm_calls: int = 0                          # apeluri Bedrock facturate
    cache_hits: int = 0
    cache_hit_rate: float = 0.0                 # % din răspunsurile LLM servite din cache
    failed_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_llm_latency_ms: int = 0
    avg_llm_latency_ms: float = 0.0             # per apel facturat
    total_cost_usd: float = 0.0
    total_cost_eur: float = 0.0
    avg_cost_per_case_usd: float = 0.0
    avg_cost_per_case_eur: float = 0.0
    cache_savings_usd: float = 0.0
    manual_minutes_per_case: float = 0.0        # presupunere: timpul unui ofițer pe un dosar
    officer_hourly_cost_eur: float = 0.0        # presupunere: costul complet al unei ore de ofițer
    manual_cost_per_case_eur: float = 0.0
    automated_cases: int = 0                    # dosare închise fără om (AUTO_PROCESSED + LIFTED)
    officer_hours_saved: float = 0.0
    manual_cost_avoided_eur: float = 0.0
    net_savings_eur: float = 0.0                # costul manual evitat minus costul AI al TUTUROR dosarelor
    roi_multiple: float | None = None           # cost manual evitat / cost AI (None cât timp AI-ul a costat 0)
    pricing: dict[str, list[float]] = Field(default_factory=dict)   # USD / 1K tokeni [input, output]


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
    ai: AiTelemetry = Field(default_factory=AiTelemetry)   # telemetrie AI & ROI
