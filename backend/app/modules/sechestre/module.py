"""Modulul Sechestre Asigurătorii — implementarea contractului LegalModule.

Procesează încheieri de sechestru asigurător civil (Art. 952-959 CPC) și ordonanțe de
sechestru asigurător penal (Art. 249-254 CPP), indisponibilizând fondurile până la
concurența sumei dispuse, cu protejarea veniturilor neurmăribile.
"""
from datetime import date
from pathlib import Path

from app.contracts import (
    AgentName, AgentStatus, BankSnapshot, Case, CaseOutcome, CaseStatus,
    DocType, HoldInstruction, ModuleInfo, ModuleStatus, ReviewAction, Severity,
)
from app.core.core_banking import CoreBankingMock
from app.core.events import EmitFn
from app.modules.popriri.agents.context import AgentContext
from app.modules.popriri.engine.rules import load_rulebook
from app.modules.popriri.graph import run_graph

SECHESTRE_RULES_PATH = str(Path(__file__).resolve().parent / "rules" / "v2026_10.yaml")


def _sechestru_response_letter(case_order, decision) -> str:
    """Generează adresa oficială de confirmare a instituirii sechestrului asigurător."""
    lines = [
        "RAIFFEISEN BANK S.A. — Departamentul Sechestre și Măsuri Asigurătorii",
        f"Data: {date.today():%d.%m.%Y}",
        f"Către: {case_order.issuer_name}",
        f"Ref.: dosar / măsură asigurătorie nr. {case_order.case_number or case_order.references_case_number}",
        "",
    ]
    if decision:
        lines += [
            f"Urmare a dispoziției de instituire a sechestrului asigurător privind debitorul/inculpatul "
            f"{case_order.debtor_name} (CNP/CUI {case_order.debtor_id}), vă confirmăm instituirea măsurii "
            f"de indisponibilizare până la concurența sumei de {case_order.total_due} RON.",
            f"În prezent, a fost înghețată (indisponibilizată în cont) suma de {decision.amount_to_hold} RON.",
            f"Suma de {decision.exempt_total} RON reprezintă venituri exceptate de la urmărire conform art. 729 CPC "
            "raportat la art. 953 CPC (alocații, indemnizații copii sau cote protejate din salariu).",
            "Sumele indisponibilizate rămân blocate în cont la dispoziția organului emitent până la "
            "comunicarea unei hotărâri definitive sau a unei dispoziții de ridicare a măsurii asigurătorii.",
        ]
    lines += [
        "",
        "Cu stimă,",
        "Departamentul Popriri, Sechestre și Executări Silite — Raiffeisen Bank S.A.",
    ]
    return "\n".join(lines)


class SechestreModule:
    info = ModuleInfo(
        module_id="sechestre",
        name="Sechestre asigurătorii",
        description=(
            "Procesarea automată a sechestrelor asigurătorii civile (Art. 952 CPC) și penale (Art. 249 CPP): "
            "identificare conturi și depozite, protecție sume exceptate, înghețare fonduri fără virare imediată."
        ),
        status=ModuleStatus.ACTIVE,
        handled_doc_types=[],
    )

    def process(
        self,
        case: Case,
        bank: BankSnapshot,
        emit: EmitFn,
        review: ReviewAction | None = None,
    ) -> Case:
        rulebook = load_rulebook(SECHESTRE_RULES_PATH)
        core_bank = CoreBankingMock(bank)
        ctx = AgentContext(bank=core_bank, emit=emit, rulebook=rulebook)

        result = run_graph(
            {
                "case_id": case.case_id,
                "document": case.document,
                "doc_type_hint": case.doc_type,
                "review": review,
            },
            ctx,
        )

        resolved = set(review.resolve_codes) if review else set()
        exceptions = []
        for e in result.get("exceptions", []):
            if e.code.value in resolved:
                e = e.model_copy(update={"resolved": True, "resolution_note": review.note if review else None})
            exceptions.append(e)

        order = result.get("order")
        decision = result.get("decision")
        outcome: CaseOutcome | None = result.get("outcome")

        blocking = [e for e in exceptions if e.severity == Severity.BLOCKING and not e.resolved]
        if not blocking and order and decision and outcome and outcome.status == CaseStatus.AUTO_PROCESSED:
            letter = _sechestru_response_letter(order, decision)
            summary = (
                f"Sechestru asigurător instituit automat: s-au înghețat {decision.amount_to_hold} RON "
                f"(până la concurența plafonului de {order.total_due} RON); {decision.amount_protected} RON "
                f"rămân protejați conform legii."
            )
            outcome = outcome.model_copy(update={"summary": summary, "response_letter_text": letter})
            emit(
                AgentName.OUTCOME,
                AgentStatus.COMPLETED,
                f"Sechestru asigurător aplicat: {decision.amount_to_hold} RON înghețați în cont",
                {"status": outcome.status.value, "summary": summary, "module": "sechestre"},
            )

        return case.model_copy(
            update={
                "module_id": "sechestre",
                "order": order,
                "customer": result.get("customer"),
                "accounts": result.get("accounts", []),
                "active_garnishments": result.get("active_garnishments", []),
                "classified_transactions": result.get("classified", []),
                "decision": decision,
                "exceptions": exceptions,
                "outcome": outcome,
                "status": outcome.status if outcome else CaseStatus.FAILED,
            }
        )
