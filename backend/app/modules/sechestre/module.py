"""Modulul Sechestre Asigurătorii — implementarea contractului LegalModule.

Procesează:
- Decizii de instituire a măsurilor asigurătorii fiscale ANAF DGAF / DGAMC (Art. 213 CPF, Formular 504)
- Încheieri civile executorii de sechestru asigurător (Art. 952-959 CPC)
- Ordonanțe de sechestru asigurător penal (Art. 249-254 CPP / Legea nr. 318/2015 ANABI)
- Decizii / încheieri de ridicare a măsurilor asigurătorii (Art. 956 CPC / Art. 213 alin. 13 CPF)
"""
from datetime import date
from pathlib import Path

from app.contracts import (
    AgentName, AgentStatus, BankSnapshot, Case, CaseOutcome, CaseStatus,
    DocType, ModuleInfo, ModuleStatus, ReviewAction, Severity,
)
from app.core.core_banking import CoreBankingMock
from app.core.events import EmitFn
from app.core.graph import run_six_agent_graph
from app.modules.popriri.agents import anomaly, income_classifier, outcome, reconciliation, rule_engine
from app.modules.popriri.agents.context import AgentContext
from app.modules.popriri.engine.rules import load_rulebook
from .extractor import run_sechestre_extraction

AGENT_DOC_TYPE = {DocType.SECHESTRU_INSTITUIRE: DocType.POPRIRE_INFIINTARE,
                  DocType.SECHESTRU_RIDICARE: DocType.POPRIRE_SISTARE}

SECHESTRE_RULES_PATH = str(Path(__file__).resolve().parent / "rules" / "v2026_10.yaml")

SECHESTRE_NODES = {
    "extraction": run_sechestre_extraction,
    "reconciliation": reconciliation.run,
    "income_classifier": income_classifier.run,
    "rule_engine": rule_engine.run,
    "anomaly": anomaly.run,
    "outcome": outcome.run,
}


def _run_sechestre_graph(initial: dict, ctx: AgentContext) -> dict:
    return run_six_agent_graph(SECHESTRE_NODES, initial, ctx)


def _sechestru_response_letter(case_order, decision) -> str:
    """Generează adresa oficială a băncii de confirmare a instituirii/ridicării sechestrului asigurător."""
    lines = [
        "RAIFFEISEN BANK S.A. — Direcția Operațiuni Juridice, Sechestre și Măsuri Asigurătorii",
        f"Data comunicării: {date.today():%d.%m.%Y}",
        f"Către: {case_order.issuer_name}",
        f"Referință dosar măsură asigurătorie nr.: {case_order.case_number or case_order.references_case_number}",
        "",
    ]
    if case_order.doc_type == DocType.POPRIRE_SISTARE:
        lines += [
            f"Vă confirmăm că, în temeiul dispoziției dumneavoastră de ridicare a măsurilor asigurătorii, "
            f"am procedat la DEBLOCAREA IMEDIATĂ a conturilor deținute de {case_order.debtor_name} "
            f"(CNP/CUI {case_order.debtor_id}), aferente dosarului nr. "
            f"{case_order.references_case_number or case_order.case_number}.",
        ]
    elif decision:
        lines += [
            f"În executarea măsurii asigurătorii a sechestrului dispuse față de debitorul/contribuabilul "
            f"{case_order.debtor_name} (CNP/CUI {case_order.debtor_id}), vă comunicăm că am instituit "
            f"indisponibilizarea disponibilităților bănești până la concurența plafonului de {case_order.total_due} RON.",
            f"Suma efectiv înghețată (indisponibilizată în cont la data prezentei): {decision.amount_to_hold} RON.",
            f"Suma exceptată legal de la urmărire și măsură asigurătorie (Art. 729 CPC raportat la Art. 953 CPC / Art. 213 CPF): "
            f"{decision.exempt_total} RON.",
            f"Contul special de consemnare indicat în actul de sechestru: {case_order.consignment_iban}.",
            "Conform regimului juridic al măsurilor asigurătorii, sumele înghețate rămân indisponibilizate în cont "
            "fără eliberare/virare până la comunicarea titlului executoriu definitiv sau a dispoziției de ridicare.",
        ]
    lines += [
        "",
        "Cu deosebită considerație,",
        "Direcția Operațiuni Juridice, Sechestre și Măsuri Asigurătorii — Raiffeisen Bank S.A.",
    ]
    return "\n".join(lines)


class SechestreModule:
    info = ModuleInfo(
        module_id="sechestre",
        name="Sechestre asigurătorii",
        description=(
            "Procesarea automată a sechestrelor asigurătorii fiscale (Art. 213 CPF), civile (Art. 952 CPC) "
            "și penale (Art. 249 CPP / ANABI): înghețare fonduri până la concurența plafonului și protecție sume exceptate."
        ),
        status=ModuleStatus.ACTIVE,
        handled_doc_types=[DocType.SECHESTRU_INSTITUIRE, DocType.SECHESTRU_RIDICARE],
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

        result = _run_sechestre_graph(
            {
                "case_id": case.case_id,
                "document": case.document,
                # agenții comuni cu PopririZero lucrează pe înființare / sistare
                "doc_type_hint": AGENT_DOC_TYPE.get(case.doc_type, case.doc_type),
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
        outcome_obj: CaseOutcome | None = result.get("outcome")

        blocking = [e for e in exceptions if e.severity == Severity.BLOCKING and not e.resolved]
        if not blocking and order and outcome_obj and outcome_obj.status in (CaseStatus.AUTO_PROCESSED, CaseStatus.LIFTED):
            letter = _sechestru_response_letter(order, decision)
            if outcome_obj.status == CaseStatus.LIFTED:
                summary = (
                    f"Măsura asigurătorie a sechestrului din dosarul "
                    f"{order.references_case_number or order.case_number} a fost ridicată; conturile au fost deblocate."
                )
            else:
                summary = (
                    f"Sechestru asigurător instituit automat: s-au înghețat {decision.amount_to_hold} RON "
                    f"(plafon măsură asigurătorie {order.total_due} RON); {decision.amount_protected} RON "
                    f"rămân protejați conform legii."
                )
            outcome_obj = outcome_obj.model_copy(update={"summary": summary, "response_letter_text": letter})
            emit(
                AgentName.OUTCOME,
                AgentStatus.COMPLETED,
                summary,
                {"status": outcome_obj.status.value, "summary": summary, "module": "sechestre"},
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
                "outcome": outcome_obj,
                "status": outcome_obj.status if outcome_obj else CaseStatus.FAILED,
            }
        )
