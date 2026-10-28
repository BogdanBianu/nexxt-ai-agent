"""Modulul PopririZero — implementarea contractului LegalModule. Proprietar: Om1."""
from app.contracts import (BankSnapshot, Case, CaseStatus, DocType, ModuleInfo, ModuleStatus, ReviewAction)
from app.core.core_banking import CoreBankingMock
from app.core.events import EmitFn
from .agents.context import AgentContext
from .engine.rules import load_rulebook
from .graph import run_graph


class PopririModule:
    info = ModuleInfo(
        module_id="popriri", name="PopririZero",
        description="Procesarea autonomă a popririlor: extragere, identificare, clasificarea veniturilor, "
                    "calcul legal (art. 729 CPC), detectarea eludării, răspuns către executor.",
        status=ModuleStatus.ACTIVE,
        handled_doc_types=[DocType.POPRIRE_INFIINTARE, DocType.POPRIRE_SISTARE, DocType.POPRIRE_MODIFICARE],
    )

    def process(self, case: Case, bank: BankSnapshot, emit: EmitFn,
                review: ReviewAction | None = None) -> Case:
        ctx = AgentContext(bank=CoreBankingMock(bank), emit=emit, rulebook=load_rulebook())
        result = run_graph({
            "case_id": case.case_id,
            "document": case.document,
            "doc_type_hint": case.doc_type,
            "review": review,
        }, ctx)

        resolved = set(review.resolve_codes) if review else set()
        exceptions = []
        for e in result.get("exceptions", []):
            if e.code.value in resolved:
                e = e.model_copy(update={"resolved": True, "resolution_note": review.note if review else None})
            exceptions.append(e)

        outcome = result.get("outcome")
        return case.model_copy(update={
            "order": result.get("order"),
            "customer": result.get("customer"),
            "accounts": result.get("accounts", []),
            "active_garnishments": result.get("active_garnishments", []),
            "classified_transactions": result.get("classified", []),
            "decision": result.get("decision"),
            "exceptions": exceptions,
            "outcome": outcome,
            "status": outcome.status if outcome else CaseStatus.FAILED,
        })
