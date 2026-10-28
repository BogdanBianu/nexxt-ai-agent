"""Corpurile cererilor și răspunsurilor HTTP care nu sunt deja în alte contracte."""
from pydantic import Field

from .common import Contract
from .enums import CaseStatus, DocType, ModuleStatus


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
