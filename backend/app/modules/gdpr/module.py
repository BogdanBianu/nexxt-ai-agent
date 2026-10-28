"""Modulul 3 LexOps: Cereri GDPR & Solicitări ANSPDCP. Proprietar: Om1.

Procesează autonom solicitările întemeiate pe Regulamentul (UE) 2016/679:
- Dreptul de acces la date (Art. 15 GDPR)
- Dreptul la ștergerea datelor / dreptul de a fi uitat (Art. 17 GDPR) coroborat cu obligațiile AML (Legea 129/2019)
- Dreptul la opoziție la marketing direct și profilare comercială (Art. 21 GDPR)
- Solicitări de investigație și controale ANSPDCP (Art. 58 GDPR)

Trece prin toți cei 6 agenți post-router:
  1. EXTRACTION        -> extrage solicitantul, calitatea, dreptul invocat (Art. 15/17/21), termenul legal (30 zile)
  2. RECONCILIATION    -> identifică clientul în Core Banking, verifică CNP-ul matematic și concordanța numelui
  3. INCOME_CLASSIFIER -> inventariază perimetrele de date (Core Banking, rulaje, marketing CRM)
  4. RULE_ENGINE       -> aplică regulile deterministe GDPR:
                          - R-GDPR-ACC-15: generare raport de date (0 RON blocați)
                          - R-GDPR-AML-17: refuz parțial ștergere conform Legii 129/2019 AML (5 ani) + ștergere CRM
                          - R-GDPR-MKT-21: opoziție imediată la comunicări de marketing
                          - R-GDPR-ANSPDCP: punere la dispoziție evidențe oficiale
  5. ANOMALY           -> verifică tentative de eludare (debitor cu popriri active care cere ștergerea datelor),
                          solicitări de la terți fără procură sau cereri abuzive/repetitive
  6. OUTCOME           -> emite decizia și redactează scrisoarea oficială de răspuns a DPO Raiffeisen Bank
"""
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
from app.core.validators import names_match, normalize_text, validate_national_id

ZERO = Decimal("0.00")

_EXTRACT_GDPR_SYSTEM = """Ești un ofițer juridic specializat în Protecția Datelor (GDPR) și DPO la Raiffeisen Bank România.
Extrage din cererea GDPR următoarele câmpuri în format JSON:
- issuer_name: "ANSPDCP" sau numele solicitantului persoană fizică
- issuer_type: "ANSPDCP" | "PERSOANA_FIZICA" | "ALTUL"
- case_number: numărul de înregistrare al cererii sau numărul adresei ANSPDCP (ex: "GDPR-2026-0891")
- issue_date: data cererii în format "YYYY-MM-DD"
- debtor_name: numele titularului persoană vizată, cu MAJUSCULE și fără diacritice (ex: "POPESCU ION")
- debtor_id: CNP-ul (13 cifre) sau CUI-ul persoanei vizate
- gdpr_right: "ACCES" | "STERGERE" | "OPOZITIE" | "PORTABILITATE" | "ANSPDCP"
- has_signature_and_stamp: true dacă există semnătură olografă, electronică sau trimitere securizată, altfel false
- has_legal_basis: true dacă este invocat Regulamentul (UE) 2016/679 sau legislația conexă de protecția datelor."""


GDPR_RIGHTS = {"ACCES", "STERGERE", "OPOZITIE", "PORTABILITATE", "ANSPDCP"}
# drepturile care TRIMIT date solicitantului: fără identitate verificată nu se răspunde automat (Art. 12 alin. 6)
DISCLOSING_RIGHTS = {"ACCES", "PORTABILITATE"}


def _is_from_anspdcp(text: str) -> bool:
    """Emitentul e ANSPDCP doar dacă apare în antet. Un client care scrie „pot sesiza ANSPDCP” rămâne client."""
    head = normalize_text(" ".join(ln for ln in text.splitlines()[:3]))
    return "ANSPDCP" in head or "AUTORITATEA NATIONALA DE SUPRAVEGHERE" in head


def _detect_gdpr_right(text: str, from_anspdcp: bool = False) -> str:
    norm = normalize_text(text)
    if from_anspdcp:
        return "ANSPDCP"
    if any(k in norm for k in ["STERGERE", "STERGEREA", "DE A FI UITAT", "ART. 17", "ART 17", "ELIMINAREA DATELOR"]):
        return "STERGERE"
    if any(k in norm for k in ["OPOZITIE", "OPUS", "MARKETING", "PROFILARE", "ART. 21", "ART 21", "DEZABONARE"]):
        return "OPOZITIE"
    if any(k in norm for k in ["PORTABILITATE", "PORTABILITATII", "ART. 20", "ART 20", "EXPORT JSON", "EXPORT CSV"]):
        return "PORTABILITATE"
    return "ACCES"


def _extract_gdpr_order(text: str) -> tuple[GarnishmentOrder, str, bool]:
    norm = normalize_text(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first_line = lines[0] if lines else "SOLICITARE GDPR"

    is_anspdcp = _is_from_anspdcp(text)
    if is_anspdcp:
        issuer_name = "AUTORITATEA NAȚIONALĂ DE SUPRAVEGHERE A PRELUCRĂRII DATELOR CU CARACTER PERSONAL (ANSPDCP)"
        issuer_type = IssuerType.ANSPDCP
    else:
        issuer_type = IssuerType.PERSOANA_FIZICA
        issuer_name = first_line[:120]

    # „Nr. înregistrare: GDPR-2026-789”; \b + cel puțin o cifră: nu prinde „nr” din interiorul cuvântului „înregistrare”
    case_m = re.search(r"\b(?:Nr\.?\s*(?:de\s+)?(?:[îi]nregistrare|adres[ăa]|lucrare)?|Dosar(?:\s+nr\.?)?|Ref\.?)"
                       r"\s*:?\s*([A-Z0-9][A-Z0-9/\-]*\d[A-Z0-9/\-]*)", text, re.I)
    date_m = re.search(r"(?:Data|București,\s*la\s*data\s*de):?\s*(\d{2}\.\d{2}\.\d{4})", text, re.I)

    text = text.replace("\\n", "\n")
    person_m = re.search(
        r"(?:Subsemnat(?:ul|a)?|Nume(?:\s+și\s+prenume)?|Persoana\s+vizat[ăa]|Titular|Client)[:\s]+([^,\n]+?)(?:,|\s+având|\s+cu)?\s*(?:CNP|C\.N\.P\.|CUI|CIF)[:\s]*([0-9]+)",
        text, re.I,
    )
    if not person_m:
        name_only = re.search(r"(?:Subsemnat(?:ul|a)?|Nume(?:\s+și\s+prenume)?):?[ \t]+([A-ZĂÂÎȘȚa-zăâîșț\s\-]+)", text)
        cnp_only = re.search(r"(?:CNP|C\.N\.P\.)[:\s]*([0-9]{13})", text)
        debtor_name = normalize_text(name_only.group(1).strip()) if name_only else None
        debtor_id = cnp_only.group(1).strip() if cnp_only else None
    else:
        debtor_name = normalize_text(person_m.group(1).strip())
        debtor_id = person_m.group(2).strip()

    if not is_anspdcp and debtor_name:
        issuer_name = f"Persoana vizată: {debtor_name}"

    has_sig = bool(re.search(r"semn[ăa]tur[ăa]|L\.S\.|autentificat|smart\s*mobile|semn[ăa]tur[ăa]\s*electronic[ăa]", text, re.I))
    legal_basis_ok = bool(re.search(r"REGULAMENT(?:UL)?\s*(?:\(UE\))?\s*(?:2016/)?679|GDPR|ART\.?\s*(?:15|17|20|21)|LEGEA\s*190/2018", norm))
    gdpr_right = _detect_gdpr_right(text, is_anspdcp)

    order = GarnishmentOrder(
        doc_type=DocType.CERERE_GDPR,
        issuer_name=issuer_name,
        issuer_type=issuer_type,
        case_number=case_m.group(1).strip() if case_m else f"GDPR-{date.today().year}-{debtor_id[-4:] if debtor_id else '0001'}",
        issue_date=datetime.strptime(date_m.group(1), "%d.%m.%Y").date() if date_m else None,
        debtor_name=debtor_name,
        debtor_id=debtor_id,
        creditor_name="Raiffeisen Bank S.A. (Operator)",
        creditor_type=CreditorType.COMERCIAL,
        principal=ZERO,
        enforcement_costs=ZERO,
        total_due=ZERO,
        consignment_iban=None,
        has_signature_and_stamp=has_sig,
        extraction_method="REGEX",
    )

    llm_data = llm.chat_json(_EXTRACT_GDPR_SYSTEM, text[:5000])
    if isinstance(llm_data, dict):
        order.extraction_method = "LLM"
        if not order.debtor_name and llm_data.get("debtor_name"):
            order.debtor_name = normalize_text(str(llm_data["debtor_name"]))
        if not order.debtor_id and llm_data.get("debtor_id"):
            order.debtor_id = re.sub(r"\D", "", str(llm_data["debtor_id"]))
        if str(llm_data.get("gdpr_right", "")).upper() in GDPR_RIGHTS and not is_anspdcp:
            gdpr_right = str(llm_data["gdpr_right"]).upper()
        if "has_legal_basis" in llm_data and not legal_basis_ok:
            legal_basis_ok = bool(llm_data["has_legal_basis"])

    order.field_confidence = {
        f: (0.98 if getattr(order, f) not in (None, "") else 0.0)
        for f in GarnishmentOrder.model_fields if f not in ("field_confidence", "extraction_method")
    }
    return order, gdpr_right, legal_basis_ok


def _gdpr_response_letter(order: GarnishmentOrder, gdpr_right: str, accounts: list,
                          transactions: list, active_garnishments: list,
                          exceptions: list[ExceptionFlag]) -> str:
    today_str = date.today().strftime("%d.%m.%Y")
    lines = [
        "RAIFFEISEN BANK S.A. — Biroul Responsabilului cu Protecția Datelor (DPO)",
        f"Data: {today_str}",
        f"Număr înregistrare: RBP/{order.case_number}",
        f"Către: {order.debtor_name or order.issuer_name}",
        f"Ref.: Solicitare privind protecția datelor cu caracter personal ({gdpr_right})",
        "",
        f"Stimate/Stimată {order.debtor_name or 'solicitant'},",
        "",
        f"Urmare a cererii dumneavoastră înregistrate la Raiffeisen Bank S.A. cu nr. {order.case_number}, "
        f"privind exercitarea drepturilor prevăzute de Regulamentul (UE) 2016/679 (GDPR), vă comunicăm următoarele decizii:",
        "",
    ]

    if gdpr_right == "ACCES":
        lines += [
            "1. DREPTUL DE ACCES (Art. 15 GDPR): Cererea dumneavoastră a fost APROBATĂ.",
            f"În evidențele băncii au fost identificate {len(accounts)} conturi bancare și {len(transactions)} operațiuni recente:",
        ]
        for a in accounts:
            lines.append(f"  • Cont {a.account_type.value} IBAN {a.iban} ({a.currency}), sold: {money(a.current_balance)} {a.currency}")
        lines += [
            "",
            "2. Scopurile prelucrării: Executarea contractelor bancare, furnizarea de servicii de plată și creditare, "
            "precum și îndeplinirea obligațiilor legale impuse de OUG 99/2006, Legea 129/2019 (AML) și Codul Fiscal.",
            "3. Destinatari ai datelor: Sistemul Național de Plăți (Reep), Biroul de Credit S.A., ANAF și BNR conform legii.",
            "4. Perioada de stocare: Pe durata relației contractuale plus 5 ani de la închiderea conturilor (conform art. 21 Legea 129/2019 AML) "
            "și 10 ani pentru documentele financiar-contabile (art. 25 Legea 82/1991).",
        ]
    elif gdpr_right == "STERGERE":
        lines += [
            "1. DREPTUL LA ȘTERGEREA DATELOR („DREPTUL DE A FI UITAT” - Art. 17 GDPR): RĂSPUNS PARȚIAL APROBAT / PARȚIAL REFUZAT.",
            "",
            "A. PRIVIND PRELUCRAREA ÎN SCOP DE MARKETING ȘI PROFILARE COMERCIALĂ: APROBAT.",
            "  • Datele dumneavoastră de contact au fost eliminate din bazele de date de marketing direct și campanii promoționale.",
            "  • Orice profilare în scopuri comerciale a fost sistată imediat.",
            "",
            "B. PRIVIND DATELE FINANCIARE, TRANZACȚIILE ȘI DOSARUL DE IDENTIFICARE CLIENT: REFUZAT ÎN TEMEI LEGAL.",
            "  • Conform Art. 17 alin. (3) lit. (b) din Regulamentul (UE) 2016/679, dreptul la ștergere NU se aplică în măsura în care "
            "prelucrarea este necesară pentru respectarea unei obligații legale care prevede prelucrarea.",
            "  • În sistemul bancar din România, banca are OBLIGAȚIA LEGALĂ IMPERATIVĂ de a păstra datele de identificare și tranzacțiile:",
            "      - Timp de 5 ANI de la încetarea relației de afaceri conform Art. 21 din Legea nr. 129/2019 pentru prevenirea spălării banilor (AML);",
            "      - Timp de 10 ANI pentru documentele justificative și registrele de contabilitate conform Art. 25 din Legea contabilității nr. 82/1991.",
            "  • De asemenea, conform Art. 17 alin. (3) lit. (e) GDPR, datele sunt necesare pentru constatarea, exercitarea sau apărarea unui drept în instanță.",
        ]
    elif gdpr_right == "OPOZITIE":
        lines += [
            "1. DREPTUL LA OPOZIȚIE (Art. 21 GDPR): Cererea dumneavoastră a fost APROBATĂ INTEGRAL.",
            "  • Am sistat orice prelucrare a datelor dumneavoastră în scopuri de marketing direct (SMS, e-mail, apeluri telefonice).",
            "  • Consimțămintele opționale din sistemul bancar (Smart Mobile / CRM) au fost revocate cu efect imediat.",
        ]
    elif gdpr_right == "ANSPDCP":
        lines += [
            "1. RĂSPUNS CĂTRE AUTORITATEA DE SUPRAVEGHERE (ANSPDCP):",
            "  • Raiffeisen Bank S.A. pune la dispoziție evidențele operațiunilor de prelucrare, jurnalul de audit și măsurile tehnice "
            "și organizatorice implementate pentru protecția datelor persoanei vizate.",
        ]
    else:
        lines.append(f"1. Solicitarea privind {gdpr_right} a fost procesată conform procedurii interne Raiffeisen Bank.")

    if active_garnishments:
        lines += [
            "",
            f"NOTĂ DE SECURITATE JURIDICĂ: Pe numele debitorului există înregistrate {len(active_garnishments)} proceduri active de executare silită / poprire. "
            "Ștergerea evidențelor financiare nu poate fi efectuată conform legii pe perioada executării silite.",
        ]

    lines += [
        "",
        "Aveți dreptul de a depune o plângere în fața Autorității Naționale de Supraveghere a Prelucrării Datelor cu Caracter Personal (ANSPDCP) "
        "la sediul din B-dul G-ral. Gheorghe Magheru 28-30, București sau pe www.dataprotection.ro.",
        "",
        "Cu stimă,",
        "Responsabilul cu Protecția Datelor (DPO) — Raiffeisen Bank S.A.",
        "Departamentul Juridic & Conformitate GDPR",
    ]
    return "\n".join(lines)


class GdprModule:
    info = ModuleInfo(
        module_id="gdpr",
        name="Cereri GDPR",
        description="Procesare autonomă a cererilor conform Regulamentului (UE) 2016/679 (acces Art. 15, ștergere Art. 17, opoziție Art. 21) și solicitărilor ANSPDCP.",
        status=ModuleStatus.ACTIVE,
        handled_doc_types=[DocType.CERERE_GDPR],
    )

    def process(self, case: Case, bank: BankSnapshot, emit: EmitFn,
                review: ReviewAction | None = None) -> Case:
        core_bank = CoreBankingMock(bank)
        resolved = set(review.resolve_codes) if review else set()
        exceptions: list[ExceptionFlag] = []

        # 1. EXTRACTION (Extragere date solicitant + temei legal GDPR)
        emit(AgentName.EXTRACTION, AgentStatus.STARTED,
             "Extrag datele din cererea GDPR și identific dreptul invocat (Art. 15/17/21)", {})
        order, gdpr_right, legal_basis_ok = _extract_gdpr_order(case.document.text or "")

        missing = [f for f in ("debtor_name", "debtor_id") if not getattr(order, f)]
        if missing:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
                message="Date obligatorii de identificare lipsă în cererea GDPR: " + ", ".join(missing),
                evidence=missing))

        if not order.has_signature_and_stamp and order.issuer_type != IssuerType.ANSPDCP:
            # acces / portabilitate trimit datele bancare: fără identitate verificată = posibilă încălcare de date
            disclosing = gdpr_right in DISCLOSING_RIGHTS
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E05_DOCUMENT_INVALID,
                severity=Severity.BLOCKING if disclosing else Severity.WARNING, agent=AgentName.EXTRACTION,
                message="Cererea nu poartă semnătură verificată sau canal autentificat 2FA (Smart Mobile)."
                        + (" Datele bancare nu se trimit până la verificarea identității solicitantului "
                           "(Art. 12 alin. (6) GDPR)." if disclosing else ""),
                evidence=["has_signature_and_stamp"]))

        if not legal_basis_ok:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.WARNING, agent=AgentName.EXTRACTION,
                message="Cererea nu citează explicit Regulamentul (UE) 2016/679, dar se procesează în baza obiectului solicitării.",
                evidence=["legal_basis"]))

        cnp_valid = validate_national_id(order.debtor_id) if order.debtor_id else False
        emit(AgentName.EXTRACTION, AgentStatus.PROGRESS,
             f"Drept GDPR identificat: {gdpr_right} · CNP {order.debtor_id}: {'VALID' if cnp_valid else 'INVALID'} · Termen legal: 30 de zile",
             {"debtor_id": order.debtor_id, "cnp_valid": cnp_valid, "gdpr_right": gdpr_right})

        if order.debtor_id and not cnp_valid:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
                message=f"CNP-ul persoanei vizate ({order.debtor_id}) este invalid matematic (cifra de control nu corespunde).",
                evidence=["debtor_id"]))

        emit(AgentName.EXTRACTION, AgentStatus.COMPLETED,
             f"Cerere GDPR: {gdpr_right} · Solicitant: {order.debtor_name} · Înreg: {order.case_number}",
             {"order": order.model_dump(mode="json"), "gdpr_right": gdpr_right,
              "exceptions": [e.code.value for e in exceptions]})

        # 2. RECONCILIATION (Identificare în Core Banking)
        emit(AgentName.RECONCILIATION, AgentStatus.STARTED,
             "Identific persoana vizată în baza de clienți și conturile asociate", {})
        if any(e.code == ExceptionCode.E01_IDENTITATE for e in exceptions):
            emit(AgentName.RECONCILIATION, AgentStatus.SKIPPED, "CNP invalid: căutarea în Core Banking a fost oprită", {})
            for ag in (AgentName.INCOME_CLASSIFIER, AgentName.RULE_ENGINE, AgentName.ANOMALY):
                emit(ag, AgentStatus.SKIPPED, "Oprire timpurie din cauza erorii de identitate (E01)", {"skipped": True})
            return self._finalize(case, order, None, [], [], [], None, exceptions, resolved, review, emit, gdpr_right)

        customer = core_bank.find_customer(order.debtor_id) if order.debtor_id else None
        if customer is None:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.RECONCILIATION,
                message=f"Persoana cu CNP {order.debtor_id} ({order.debtor_name}) nu figurează în baza de clienți Raiffeisen Bank.",
                evidence=["debtor_id"]))
            emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED, "Persoana vizată nu figurează în evidențele băncii", {})
            for ag in (AgentName.INCOME_CLASSIFIER, AgentName.RULE_ENGINE, AgentName.ANOMALY):
                emit(ag, AgentStatus.SKIPPED, "Persoana nu deține date financiare în bancă", {"skipped": True})
            return self._finalize(case, order, None, [], [], [], None, exceptions, resolved, review, emit, gdpr_right)

        if not names_match(customer.full_name, order.debtor_name):
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.RECONCILIATION,
                message=f"Numele din cererea GDPR ({order.debtor_name}) nu corespunde titularului CNP-ului din bancă ({customer.full_name}).",
                evidence=["debtor_name"]))

        if customer.status != CustomerStatus.ACTIV:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E08_STATUT_CLIENT, severity=Severity.WARNING, agent=AgentName.RECONCILIATION,
                message=f"Titularul figurează cu statutul special {customer.status.value}.",
                evidence=[customer.customer_id]))

        accounts = core_bank.get_accounts(customer.customer_id)
        transactions = core_bank.get_transactions(customer.customer_id)
        active_garnishments = core_bank.get_active_garnishments(customer.customer_id)
        emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED,
             f"Client identificat: {customer.full_name} ({len(accounts)} conturi, {len(transactions)} tranzacții, {len(active_garnishments)} popriri active)",
             {"customer_id": customer.customer_id, "accounts": len(accounts), "active_garnishments": len(active_garnishments)})

        # 3. INCOME_CLASSIFIER (Inventarierea perimetrelor de date: Core Banking, Tranzacții, Marketing)
        emit(AgentName.INCOME_CLASSIFIER, AgentStatus.STARTED,
             "Inventariez perimetrele de date personale (conturi, istoric tranzacțional, acorduri marketing)", {})
        classified: list[ClassifiedTransaction] = []
        ref_date = order.issue_date or case.document.received_at.date()
        for acc in accounts:
            bal = to_ron(acc.current_balance, acc.currency)
            classified.append(ClassifiedTransaction(
                tx_id=f"PERIMETRU-CORE-{acc.iban[-6:]}",
                iban=acc.iban,
                booking_date=ref_date,
                amount=bal,
                counterparty_name="Raiffeisen Core Banking",
                description=f"Perimetru Core Banking: Cont {acc.account_type.value} ({acc.currency}) cu sold {money(bal)} RON",
                category=IncomeCategory.SOLD_ANTERIOR,
                method=ClassificationMethod.PATTERN,
                confidence=1.0,
                rationale="Date contractuale și solduri stocate pe durata contractului conform OUG 99/2006.",
            ))
        for t in sorted(transactions, key=lambda t: t.booking_date, reverse=True)[:10]:   # cele mai recente
            classified.append(ClassifiedTransaction(
                tx_id=t.tx_id,
                iban=t.iban,
                booking_date=t.booking_date,
                amount=t.amount,
                counterparty_name=t.counterparty_name,
                description=f"Perimetru Tranzacții: {t.description}",
                category=IncomeCategory.ALT_VENIT,
                method=ClassificationMethod.PATTERN,
                confidence=0.95,
                rationale="Date tranzacționale supuse arhivării obligatorii de 5 ani conform Legii 129/2019 (AML).",
            ))
        classified.append(ClassifiedTransaction(
            tx_id=f"PERIMETRU-CRM-{customer.customer_id}",
            iban=accounts[0].iban if accounts else "RO00RAIF0000000000000000",
            booking_date=ref_date,
            amount=ZERO,
            counterparty_name="Raiffeisen CRM & Marketing",
            description="Perimetru Marketing: Profilare comercială, scoring campanii, consimțăminte directe",
            category=IncomeCategory.ALT_VENIT,
            method=ClassificationMethod.PATTERN,
            confidence=1.0,
            rationale="Date de marketing bazate pe consimțământ (Art. 6(1)(a) GDPR) - pot fi revocate/șterse oricând.",
        ))
        emit(AgentName.INCOME_CLASSIFIER, AgentStatus.COMPLETED,
             f"Inventariate 3 perimetre de date (Core Banking, Tranzacții AML, Marketing CRM)",
             {"perimeters": ["CoreBanking", "TransactionsAML", "MarketingCRM"], "positions": len(classified)})

        # 4. RULE_ENGINE (Reguli deterministe GDPR vs Legislație bancară)
        emit(AgentName.RULE_ENGINE, AgentStatus.STARTED,
             f"Aplic regulile deterministe pentru cererea de tip {gdpr_right}", {})
        total_balance = sum((to_ron(a.current_balance, a.currency) for a in accounts), ZERO)
        rules_applied: list[RuleApplication] = []

        if gdpr_right == "STERGERE":
            rules_applied.append(RuleApplication(
                rule_id="R-GDPR-AML-17",
                legal_source="Art. 17 alin. (3) lit. (b) GDPR & Art. 21 Legea 129/2019 AML & Art. 25 Legea 82/1991",
                description="Refuz parțial de ștergere: datele financiare și KYC se păstrează obligatoriu 5 ani (AML) / 10 ani (contabilitate). Se aprobă ștergerea exclusivă a datelor de marketing din CRM.",
                base_amount=money(total_balance),
                seizable_amount=ZERO,
                tx_ids=[c.tx_id for c in classified],
            ))
        elif gdpr_right == "OPOZITIE":
            rules_applied.append(RuleApplication(
                rule_id="R-GDPR-MKT-21",
                legal_source="Art. 21 alin. (2)-(3) Regulamentul (UE) 2016/679",
                description="Opoziție la marketing direct și profilare: revocare imediată a consimțămintelor comerciale în CRM. Fără afectarea contractelor bancare.",
                base_amount=ZERO,
                seizable_amount=ZERO,
                tx_ids=[f"PERIMETRU-CRM-{customer.customer_id}"],
            ))
        elif gdpr_right == "ANSPDCP":
            rules_applied.append(RuleApplication(
                rule_id="R-GDPR-ANSPDCP",
                legal_source="Art. 58 Regulamentul (UE) 2016/679 & Legea 102/2005",
                description="Comunicare evidențe și jurnal de audit către Autoritatea de Supraveghere.",
                base_amount=ZERO,
                seizable_amount=ZERO,
                tx_ids=[c.tx_id for c in classified],
            ))
        else:  # ACCES / PORTABILITATE
            rules_applied.append(RuleApplication(
                rule_id="R-GDPR-ACC-15",
                legal_source="Art. 15 Regulamentul (UE) 2016/679",
                description="Furnizare raport complet de date cu caracter personal, categorii prelucrate și destinatari legali.",
                base_amount=money(total_balance),
                seizable_amount=ZERO,
                tx_ids=[c.tx_id for c in classified],
            ))

        decision = GarnishmentDecision(
            periodic_income=ZERO,
            seizable_periodic=ZERO,
            seizable_other=ZERO,
            exempt_total=money(total_balance),
            amount_to_hold=ZERO,
            amount_protected=money(total_balance),
            total_due=ZERO,
            rules_applied=rules_applied,
            allocations=[],
            hold_instructions=[],
            rules_version="2026.10-GDPR",
        )
        emit(AgentName.RULE_ENGINE, AgentStatus.COMPLETED,
             f"Regula {rules_applied[0].rule_id} aplicată: 0.00 RON blocați · Decizie conformă GDPR",
             {"rule_id": rules_applied[0].rule_id, "amount_to_hold": 0.0})

        # 5. ANOMALY (Verificare tentativă de eludare a popririlor sau fraudă)
        emit(AgentName.ANOMALY, AgentStatus.STARTED,
             "Verific potențialul de fraudă sau eludare a executării silite (popriri active)", {})
        if gdpr_right == "STERGERE" and active_garnishments:
            garn_cases = [g.case_number for g in active_garnishments]
            anom_exc = ExceptionFlag(
                code=ExceptionCode.E06_SUSPICIUNE_ELUDARE,
                severity=Severity.BLOCKING,
                agent=AgentName.ANOMALY,
                message=f"Tentativă suspectă de eludare: clientul solicită ștergerea datelor („dreptul de a fi uitat”), "
                        f"având {len(active_garnishments)} dosare de poprire activă ({', '.join(garn_cases)}). "
                        "Ștergerea evidențelor este interzisă până la finalizarea executării silite.",
                evidence=garn_cases,
            )
            exceptions.append(anom_exc)
            emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
                 f"Alertă E06 ridicată: cerere de ștergere pe client cu poprire activă ({len(active_garnishments)} dosare)",
                 {"exception": "E06", "active_garnishments": len(active_garnishments)})
        else:
            emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
                 "Nicio tentativă de eludare identificată; profil de risc conform", {"anomalies": 0})

        return self._finalize(case, order, customer, accounts, active_garnishments,
                               classified, decision, exceptions, resolved, review, emit,
                               gdpr_right, transactions)

    def _finalize(self, case: Case, order: GarnishmentOrder, customer, accounts: list,
                  active_garnishments: list, classified: list, decision: GarnishmentDecision | None = None,
                  exceptions: list[ExceptionFlag] | None = None, resolved: set[str] | None = None,
                  review: ReviewAction | None = None, emit: EmitFn | None = None,
                  gdpr_right: str = "ACCES", transactions: list | None = None) -> Case:
        exceptions = exceptions or []
        resolved = resolved or set()
        transactions = transactions or []

        # 6. OUTCOME (Decizie finală + Scrisoare oficială DPO Raiffeisen)
        if emit:
            emit(AgentName.OUTCOME, AgentStatus.STARTED,
                 "Generez răspunsul oficial DPO Raiffeisen Bank conform Regulamentului (UE) 2016/679", {})

        final_exceptions: list[ExceptionFlag] = []
        for e in exceptions:
            if e.code.value in resolved:
                e = e.model_copy(update={"resolved": True, "resolution_note": review.note if review else None})
            final_exceptions.append(e)

        blocking = [e for e in final_exceptions if e.severity == Severity.BLOCKING and not e.resolved]
        if blocking:
            status = CaseStatus.EXCEPTION_FLAGGED
            summary = (f"Cererea GDPR ({order.case_number}) a fost oprită pentru validare DPO / ofițer juridic: "
                       f"{len(blocking)} excepții ({', '.join(sorted({e.code.value for e in blocking}))}). "
                       f"Motiv: {blocking[0].message}")
            letter = None
        else:
            status = CaseStatus.AUTO_PROCESSED
            action_desc = "Răspuns parțial aprobat (menținere date AML + ștergere CRM)" if gdpr_right == "STERGERE" else f"Cerere {gdpr_right} aprobată"
            summary = (f"Cerere GDPR ({gdpr_right}) procesată autonom pentru {order.debtor_name} (înreg. {order.case_number}): "
                       f"{action_desc}, 0.00 RON blocați, răspuns oficial DPO redactat.")
            letter = _gdpr_response_letter(order, gdpr_right, accounts, transactions, active_garnishments, final_exceptions)

        outcome = CaseOutcome(status=status, summary=summary, response_letter_text=letter)
        if emit:
            emit(AgentName.OUTCOME, AgentStatus.COMPLETED, f"Rezultat: {status.value}",
                 {"status": status.value, "summary": summary, "gdpr_right": gdpr_right})

        return case.model_copy(update={
            "order": order,
            "customer": customer,
            "accounts": accounts,
            "active_garnishments": active_garnishments,
            "classified_transactions": classified,
            "decision": decision,
            "exceptions": final_exceptions,
            "outcome": outcome,
            "status": status,
        })
