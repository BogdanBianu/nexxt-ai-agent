"""Modulul 2 LexOps: Cereri Autorități (Poliție, Parchet, DNA, DIICOT, ANAF Antifraudă). Proprietar: Om1.

Procesează autonom solicitările de informații și rulaje bancare în dosare penale (Art. 170 Cod Procedură Penală),
rulate prin graful LangGraph cu cei 6 agenți post-router:
  1. EXTRACTION        -> extrage emitentul, nr. dosar penal, persoana vizată, CNP/CUI + verifică temeiul legal (secretul bancar)
  2. RECONCILIATION    -> identifică persoana în Core Banking, verifică numele și încarcă conturile/tranzacțiile
  3. INCOME_CLASSIFIER -> inventariază soldurile și rulajele din conturi pentru raportul către autoritate
  4. RULE_ENGINE       -> aplică regula R-CPP-170 (comunicare date fără blocare de sume: amount_to_hold = 0 RON)
  5. ANOMALY           -> scanează tranzacțiile după operațiuni suspecte AML / ONPCSB solicitate de organul penal
  6. OUTCOME           -> emite decizia și redactează adresa oficială de răspuns Raiffeisen Bank către IGPR/Parchet
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re

from app.contracts import (
    AgentName, AgentStatus, BankSnapshot, Case, CaseOutcome, CaseStatus, ClassificationMethod,
    ClassifiedTransaction, CreditorType, CustomerStatus, DocType, ExceptionCode, ExceptionFlag,
    GarnishmentDecision, GarnishmentOrder, IncomeCategory, IssuerType, ModuleInfo, ModuleStatus,
    ReviewAction, RuleApplication, Severity, TxDirection, money,
)
from app.core import llm
from app.core.core_banking import CoreBankingMock, to_ron
from app.core.events import EmitFn
from app.core.graph import run_six_agent_graph
from app.core.validators import names_match, normalize_text, validate_national_id

ZERO = Decimal("0.00")


@dataclass
class _AutoritatiContext:
    bank: CoreBankingMock
    emit: EmitFn


_EXTRACT_SYSTEM = """Ești un agent AI juridic din Raiffeisen Bank România specializat în procesarea solicitărilor de la autorități (Poliție, Parchet, DNA, DIICOT) în dosare penale.
Extrage din document următoarele câmpuri în format JSON:
- issuer_name: instituția emitentă (ex: "INSPECTORATUL GENERAL AL POLIȚIEI ROMÂNE")
- issuer_type: "POLITIE" | "PARCHET" | "ANAF" | "ALTUL"
- case_number: numărul dosarului penal / lucrării (ex: "445566/P/2026")
- issue_date: data emiterii în format "YYYY-MM-DD"
- debtor_name: numele persoanei vizate, cu MAJUSCULE și fără diacritice (ex: "VASILESCU DANIEL")
- debtor_id: CNP-ul (13 cifre) sau CUI-ul persoanei vizate
- has_signature_and_stamp: true dacă documentul are semnătură și ștampilă / L.S., altfel false
- has_legal_basis: true dacă documentul invocă un temei legal valid pentru ridicarea secretului bancar (ex: art. 170 Cod Procedură Penală, ordonanță procuror, mandat judecător), altfel false."""

_LEGAL_BASIS_PATTERNS = [
    r"ART\.?\s*170",
    r"COD(?:UL)?\s+DE\s+PROCEDURA\s+PENALA",
    r"COD\s+PROCEDURA\s+PENALA",
    r"ORDONANTA\s+PROCUROR",
    r"MANDAT",
    r"AUTORIZATIE\s+JUDECATOR",
]


def _has_legal_basis(text: str) -> bool:
    norm = normalize_text(text)
    return any(re.search(pat, norm) for pat in _LEGAL_BASIS_PATTERNS)


def _extract_authority_order(text: str) -> tuple[GarnishmentOrder, bool]:
    norm = normalize_text(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first_line = lines[0] if lines else "AUTORITATE PUBLICĂ"
    second_line = lines[1] if len(lines) > 1 and not re.search(r"DOSAR|DATA|CATRE", normalize_text(lines[1])) else ""
    issuer_name = f"{first_line} — {second_line}".strip(" —")[:120] if second_line else first_line[:120]

    if "PARCHET" in norm or "DNA" in norm or "DIICOT" in norm or "ANTICORUPTIE" in norm:
        issuer_type = IssuerType.PARCHET
    elif "POLITIE" in norm or "POLITIA" in norm or "IGPR" in norm or "IPJ" in norm:
        issuer_type = IssuerType.POLITIE
    elif "ANAF" in norm or "ANTIFRAUDA" in norm or "FISCAL" in norm:
        issuer_type = IssuerType.ANAF
    else:
        issuer_type = IssuerType.ALTUL

    case_m = re.search(r"(?:Dosar(?:\s+penal)?|Lucrarea)\s+nr\.?\s*([0-9A-Z/\-]+)", text, re.I)
    date_m = re.search(r"Data:\s*(\d{2}\.\d{2}\.\d{4})", text, re.I)
    person_m = re.search(
        r"(?:Nume(?:\s+și\s+prenume)?|Persoana\s+vizat[ăa]|Suspect|Inculpat|Debitor|Titular):[ \t]*([^,\n]+),\s*(?:CNP|C\.N\.P\.|CUI|CIF)[:\s]*([0-9]+)",
        text, re.I,
    )
    has_sig = bool(re.search(r"semn[ăa]tur[ăa] [șs]i [șs]tampil[ăa]|L\.S\.|semn[ăa]tur[ăa] electronic[ăa]", text, re.I))
    legal_ok = _has_legal_basis(text)

    order = GarnishmentOrder(
        doc_type=DocType.CERERE_AUTORITATE,
        issuer_name=issuer_name,
        issuer_type=issuer_type,
        case_number=case_m.group(1).strip() if case_m else None,
        issue_date=datetime.strptime(date_m.group(1), "%d.%m.%Y").date() if date_m else None,
        debtor_name=normalize_text(person_m.group(1)) if person_m else None,
        debtor_id=person_m.group(2).strip() if person_m else None,
        creditor_name=issuer_name,
        creditor_type=CreditorType.FISCAL,
        principal=ZERO,
        enforcement_costs=ZERO,
        total_due=ZERO,
        consignment_iban=None,
        has_signature_and_stamp=has_sig,
        extraction_method="REGEX",
    )

    llm_data = llm.chat_json(_EXTRACT_SYSTEM, text[:5000])
    if isinstance(llm_data, dict):
        order.extraction_method = "LLM"
        if not order.case_number and llm_data.get("case_number"):
            order.case_number = str(llm_data["case_number"]).strip()
        if not order.debtor_name and llm_data.get("debtor_name"):
            order.debtor_name = normalize_text(str(llm_data["debtor_name"]))
        if not order.debtor_id and llm_data.get("debtor_id"):
            order.debtor_id = re.sub(r"\D", "", str(llm_data["debtor_id"]))
        if "has_legal_basis" in llm_data and not legal_ok:
            legal_ok = bool(llm_data["has_legal_basis"])

    order.field_confidence = {
        f: (0.97 if getattr(order, f) not in (None, "") else 0.0)
        for f in GarnishmentOrder.model_fields if f not in ("field_confidence", "extraction_method")
    }
    return order, legal_ok


def _authority_response_letter(order: GarnishmentOrder, accounts: list, transactions: list,
                               aml_flags: list[ExceptionFlag]) -> str:
    acc_lines = []
    for a in accounts:
        acc_lines.append(
            f"  • Cont {a.account_type.value} IBAN {a.iban} ({a.currency}): "
            f"sold curent {money(a.current_balance)} {a.currency} (sold inițial perioadă: {money(a.opening_balance)} {a.currency})"
        )
    if not acc_lines:
        acc_lines.append("  • Nu au fost identificate conturi active deschise pe numele persoanei vizate.")

    aml_line = (
        f"3. Operațiuni suspecte (AML / ONPCSB): Au fost identificate {len(aml_flags)} alerte de tranzacționare atipică "
        f"({'; '.join(e.message for e in aml_flags)})."
        if aml_flags else
        "3. Operațiuni suspecte (AML / ONPCSB): Nu au fost înregistrate raportări de tranzacții suspecte către ONPCSB în perioada analizată."
    )

    lines = [
        "RAIFFEISEN BANK S.A. — Departamentul Juridic & Conformitate Autorități",
        f"Data: {date.today():%d.%m.%Y}",
        "Regim: CONFIDENȚIAL — SECRET BANCAR (Art. 170 Cod Procedură Penală)",
        f"Către: {order.issuer_name}",
        f"Ref.: Dosar penal nr. {order.case_number}",
        "",
        f"Urmare a solicitării dumneavoastră formulate în dosarul penal nr. {order.case_number}, în temeiul art. 170 Cod Procedură Penală, "
        f"privind persoana vizată {order.debtor_name} (CNP/CUI {order.debtor_id}), vă comunicăm următoarele date din evidențele Raiffeisen Bank S.A.:",
        "",
        "1. Situația conturilor bancare identificate:",
        *acc_lines,
        "",
        f"2. Rulaje și extrase de cont: În perioada analizată au fost identificate {len(transactions)} operațiuni bancare (anexate în format electronic).",
        aml_line,
        "",
        "Menționăm că prezenta adresă reprezintă o comunicare de informații conform art. 170 CPP și nu implică indisponibilizarea sumelor din cont "
        "(0,00 RON blocați, în absența unei ordonanțe de instituire a sechestrului asigurător conform art. 249 CPP).",
        "",
        "Cu stimă,",
        "Departamentul Operațiuni Juridice șiRăspuns Autorități — Raiffeisen Bank S.A.",
    ]
    return "\n".join(lines)


def _node_extraction(state: dict, ctx: _AutoritatiContext) -> dict:
    emit = ctx.emit
    emit(AgentName.EXTRACTION, AgentStatus.STARTED,
         "Extrag datele din solicitarea autorității și verific temeiul legal (secretul bancar)", {})
    order, legal_ok = _extract_authority_order(state["document"].text or "")
    exceptions: list[ExceptionFlag] = []

    missing = [f for f in ("case_number", "debtor_name", "debtor_id") if not getattr(order, f)]
    if missing:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message="Câmpuri obligatorii lipsă în solicitarea autorității: " + ", ".join(missing),
            evidence=missing))
    if not order.has_signature_and_stamp:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message="Solicitarea nu poartă semnătură și ștampilă oficială a organului de urmărire penală.",
            evidence=["has_signature_and_stamp"]))
    if not legal_ok:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message="Temei legal lipsă: divulgarea datelor protejate de secretul bancar necesită invocarea Art. 170 CPP sau a unei ordonanțe/autorizații valide.",
            evidence=["legal_basis"]))

    cnp_valid = validate_national_id(order.debtor_id) if order.debtor_id else False
    emit(AgentName.EXTRACTION, AgentStatus.PROGRESS,
         f"Validare CNP/CUI persoană vizată ({order.debtor_id}): {'VALID' if cnp_valid else 'INVALID'} · Temei Art. 170 CPP: {'DA' if legal_ok else 'LIPSĂ'}",
         {"debtor_id": order.debtor_id, "cnp_valid": cnp_valid, "has_legal_basis": legal_ok})

    if order.debtor_id and not cnp_valid:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message=f"CNP/CUI-ul persoanei vizate ({order.debtor_id}) este invalid matematic (cifra de control nu corespunde).",
            evidence=["debtor_id"]))

    emit(AgentName.EXTRACTION, AgentStatus.COMPLETED,
         f"Dosar penal {order.case_number} · {order.issuer_name} · Persoană vizată: {order.debtor_name}",
         {"order": order.model_dump(mode="json"), "exceptions": [e.code.value for e in exceptions]})
    return {"order": order, "exceptions": exceptions}


def _node_reconciliation(state: dict, ctx: _AutoritatiContext) -> dict:
    emit = ctx.emit
    order = state["order"]
    emit(AgentName.RECONCILIATION, AgentStatus.STARTED,
         "Caut persoana vizată și conturile asociate în Core Banking", {})
    if any(e.code == ExceptionCode.E01_IDENTITATE for e in state.get("exceptions", [])):
        emit(AgentName.RECONCILIATION, AgentStatus.SKIPPED, "CNP invalid: căutarea în Core Banking a fost oprită", {})
        return {
            "customer": None,
            "accounts": [],
            "transactions": [],
            "active_garnishments": [],
            "stop_after_reconciliation": True,
            "skip_reason": "Oprire timpurie din cauza erorii de identitate (E01)",
        }

    customer = ctx.bank.find_customer(order.debtor_id) if order.debtor_id else None
    if customer is None:
        exc = ExceptionFlag(
            code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.RECONCILIATION,
            message=f"Persoana cu CNP/CUI {order.debtor_id} ({order.debtor_name}) nu figurează în baza de clienți Raiffeisen Bank.",
            evidence=["debtor_id"])
        emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED, "Persoana vizată nu este client al băncii", {})
        return {
            "customer": None,
            "accounts": [],
            "transactions": [],
            "active_garnishments": [],
            "exceptions": [exc],
            "stop_after_reconciliation": True,
            "skip_reason": "Persoana nu deține conturi în bancă",
        }

    exceptions: list[ExceptionFlag] = []
    if not names_match(customer.full_name, order.debtor_name):
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.RECONCILIATION,
            message=f"Numele din solicitarea penală ({order.debtor_name}) nu corespunde titularului CNP-ului din bancă ({customer.full_name}).",
            evidence=["debtor_name"]))

    if customer.status != CustomerStatus.ACTIV:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E08_STATUT_CLIENT, severity=Severity.WARNING, agent=AgentName.RECONCILIATION,
            message=f"Titularul figurează cu statutul special {customer.status.value}.",
            evidence=[customer.customer_id]))

    accounts = ctx.bank.get_accounts(customer.customer_id)
    transactions = ctx.bank.get_transactions(customer.customer_id)
    active_garnishments = ctx.bank.get_active_garnishments(customer.customer_id)
    emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED,
         f"Client identificat: {customer.full_name} ({len(accounts)} conturi active, {len(transactions)} tranzacții)",
         {"customer_id": customer.customer_id, "accounts": len(accounts), "transactions": len(transactions)})
    return {
        "customer": customer,
        "accounts": accounts,
        "transactions": transactions,
        "active_garnishments": active_garnishments,
        "exceptions": exceptions,
        "stop_after_reconciliation": False,
    }


def _node_income_classifier(state: dict, ctx: _AutoritatiContext) -> dict:
    emit = ctx.emit
    order = state["order"]
    accounts = state.get("accounts", [])
    transactions = state.get("transactions", [])
    emit(AgentName.INCOME_CLASSIFIER, AgentStatus.STARTED,
         "Inventariez soldurile și rulajele conturilor solicitate în dosarul penal", {})
    classified: list[ClassifiedTransaction] = []
    ref_date = order.issue_date or state["document"].received_at.date()
    for acc in accounts:
        bal = to_ron(acc.current_balance, acc.currency)
        if bal > ZERO:
            classified.append(ClassifiedTransaction(
                tx_id=f"SOLD-{acc.iban[-6:]}",
                iban=acc.iban,
                booking_date=ref_date,
                amount=bal,
                counterparty_name="—",
                description=f"Sold curent disponibil în contul {acc.account_type.value} ({acc.currency})",
                category=IncomeCategory.SOLD_ANTERIOR,
                method=ClassificationMethod.PATTERN,
                confidence=1.0,
                rationale="Sold identificat pentru raportarea către autoritatea solicitantă (Art. 170 CPP).",
            ))
    for t in transactions:
        if t.direction == TxDirection.CREDIT:
            classified.append(ClassifiedTransaction(
                tx_id=t.tx_id,
                iban=t.iban,
                booking_date=t.booking_date,
                amount=t.amount,
                counterparty_name=t.counterparty_name,
                description=t.description,
                category=IncomeCategory.ALT_VENIT,
                method=ClassificationMethod.PATTERN,
                confidence=0.95,
                rationale="Rulaj creditor inclus în extrasul comunicat organului de urmărire penală.",
            ))
    emit(AgentName.INCOME_CLASSIFIER, AgentStatus.COMPLETED,
         f"{len(accounts)} conturi și {len(classified)} poziții financiare pregătite pentru raportare",
         {"positions": len(classified)})
    return {"classified": classified}


def _node_rule_engine(state: dict, ctx: _AutoritatiContext) -> dict:
    emit = ctx.emit
    classified = state.get("classified", [])
    emit(AgentName.RULE_ENGINE, AgentStatus.STARTED,
         "Aplic regulile privind secretul bancar și comunicarea de date (Art. 170 CPP)", {})
    total_balance = sum((c.amount for c in classified), ZERO)
    cpp_rule = RuleApplication(
        rule_id="R-CPP-170",
        legal_source="Art. 170 Cod Procedură Penală & Art. 113 OUG 99/2006",
        description="Comunicare date și extrase de cont către organul de urmărire penală fără indisponibilizare de sume (fără sechestru asigurător Art. 249 CPP).",
        base_amount=money(total_balance),
        seizable_amount=ZERO,
        tx_ids=[c.tx_id for c in classified],
    )
    decision = GarnishmentDecision(
        periodic_income=ZERO,
        seizable_periodic=ZERO,
        seizable_other=ZERO,
        exempt_total=money(total_balance),
        amount_to_hold=ZERO,
        amount_protected=money(total_balance),
        total_due=ZERO,
        rules_applied=[cpp_rule],
        allocations=[],
        hold_instructions=[],
        rules_version="2026.10-CPP",
    )
    emit(AgentName.RULE_ENGINE, AgentStatus.COMPLETED,
         f"Regula R-CPP-170 aplicată: 0.00 RON indisponibilizați · {money(total_balance)} RON raportați în extras",
         {"rule_id": "R-CPP-170", "amount_to_hold": 0.0, "reported_balance": float(total_balance)})
    return {"decision": decision}


def _node_anomaly(state: dict, ctx: _AutoritatiContext) -> dict:
    emit = ctx.emit
    transactions = state.get("transactions", [])
    emit(AgentName.ANOMALY, AgentStatus.STARTED,
         "Verific istoricul operațiunilor suspecte (AML / ONPCSB) solicitate de organul penal", {})
    aml_flags: list[ExceptionFlag] = []
    large_debits = [t for t in transactions if t.direction == TxDirection.DEBIT and t.amount >= Decimal("10000")]
    if large_debits:
        total_out = sum((t.amount for t in large_debits), ZERO)
        aml_exc = ExceptionFlag(
            code=ExceptionCode.E06_SUSPICIUNE_ELUDARE,
            severity=Severity.WARNING,
            agent=AgentName.ANOMALY,
            message=f"Alertă AML / ONPCSB: {len(large_debits)} ieșiri mari din cont însumând {money(total_out)} RON către {large_debits[0].counterparty_name}.",
            evidence=[t.tx_id for t in large_debits],
        )
        aml_flags.append(aml_exc)
    emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
         f"{len(aml_flags)} alerte AML identificate pentru raportul ONPCSB" if aml_flags else "Nicio alertă AML/ONPCSB în istoricul clientului",
         {"aml_alerts": len(aml_flags)})
    return {"aml_flags": aml_flags, "exceptions": aml_flags}


def _node_outcome(state: dict, ctx: _AutoritatiContext) -> dict:
    emit = ctx.emit
    order = state["order"]
    accounts = state.get("accounts", [])
    transactions = state.get("transactions", [])
    decision = state.get("decision")
    aml_flags = state.get("aml_flags", [])
    review = state.get("review")
    resolved = set(review.resolve_codes) if review else set()

    emit(AgentName.OUTCOME, AgentStatus.STARTED,
         "Generez răspunsul oficial Raiffeisen Bank către autoritatea solicitantă", {})

    blocking = [
        e for e in state.get("exceptions", [])
        if e.severity == Severity.BLOCKING and not e.resolved and e.code.value not in resolved
    ]
    if blocking:
        status = CaseStatus.EXCEPTION_FLAGGED
        summary = (f"Solicitarea autorității ({order.case_number or 'fără număr'}) a fost oprită pentru verificare juridică: "
                   f"{len(blocking)} excepții blocante ({', '.join(sorted({e.code.value for e in blocking}))}). "
                   "Nu s-au comunicat date protejate de secretul bancar.")
        letter = None
    else:
        status = CaseStatus.AUTO_PROCESSED
        total_rep = decision.amount_protected if decision else ZERO
        summary = (f"Solicitare Art. 170 CPP procesată automat pentru dosarul penal {order.case_number}: "
                   f"au fost identificate {len(accounts)} conturi (sold total {money(total_rep)} RON, 0.00 RON blocați) "
                   f"și s-a generat adresa oficială de răspuns către {order.issuer_name}.")
        letter = _authority_response_letter(order, accounts, transactions, aml_flags)

    outcome = CaseOutcome(status=status, summary=summary, response_letter_text=letter)
    emit(AgentName.OUTCOME, AgentStatus.COMPLETED, f"Rezultat: {status.value}",
         {"status": status.value, "summary": summary})
    return {"outcome": outcome}


AUTORITATI_NODES = {
    "extraction": _node_extraction,
    "reconciliation": _node_reconciliation,
    "income_classifier": _node_income_classifier,
    "rule_engine": _node_rule_engine,
    "anomaly": _node_anomaly,
    "outcome": _node_outcome,
}


class AutoritatiModule:
    info = ModuleInfo(
        module_id="autoritati",
        name="Cereri autorități",
        description="Solicitări de informații, rulaje și verificări AML de la Poliție (IGPR/IPJ), Parchet, DNA, DIICOT și ANAF Antifraudă (Art. 170 CPP).",
        status=ModuleStatus.ACTIVE,
        handled_doc_types=[DocType.CERERE_AUTORITATE],
    )

    def process(self, case: Case, bank: BankSnapshot, emit: EmitFn,
                review: ReviewAction | None = None) -> Case:
        ctx = _AutoritatiContext(bank=CoreBankingMock(bank), emit=emit)
        result = run_six_agent_graph(AUTORITATI_NODES, {
            "case_id": case.case_id,
            "document": case.document,
            "doc_type_hint": case.doc_type,
            "review": review,
        }, ctx)

        resolved = set(review.resolve_codes) if review else set()
        final_exceptions: list[ExceptionFlag] = []
        for e in result.get("exceptions", []):
            if e.code.value in resolved:
                e = e.model_copy(update={"resolved": True, "resolution_note": review.note if review else None})
            final_exceptions.append(e)

        outcome = result.get("outcome")
        return case.model_copy(update={
            "order": result.get("order"),
            "customer": result.get("customer"),
            "accounts": result.get("accounts", []),
            "active_garnishments": result.get("active_garnishments", []),
            "classified_transactions": result.get("classified", []),
            "decision": result.get("decision"),
            "exceptions": final_exceptions,
            "outcome": outcome,
            "status": outcome.status if outcome else CaseStatus.FAILED,
        })
