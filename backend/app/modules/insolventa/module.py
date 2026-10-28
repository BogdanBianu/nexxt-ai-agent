"""Modulul LexOps „Insolvență și succesiuni”. Proprietar: Om2.

Două tipuri de documente, aceiași 6 agenți post-router:

NOTIFICARE_INSOLVENTA (tribunal / administrator / lichidator judiciar, Legea 85/2014)
  1. EXTRACTION        -> tribunal, nr. dosar, debitor (CUI), practician, data deschiderii, contul de insolvență
  2. RECONCILIATION    -> debitorul în Core Banking; dacă nu e client, răspundem că nu deține conturi
  3. INCOME_CLASSIFIER -> inventarul soldurilor (intră în averea debitorului)
  4. RULE_ENGINE       -> R-INS-01 suspendă popririle active, R-INS-02 marchează conturile INSOLVENTA
  5. ANOMALY           -> plăți ieșite din cont după deschiderea procedurii
  6. OUTCOME           -> răspunsul către administratorul / lichidatorul judiciar

CERTIFICAT_MOSTENITOR (notar public)
  1. EXTRACTION        -> notar, nr. certificat, defunct, data decesului, moștenitori + cote (suma = 1)
  2. RECONCILIATION    -> defunctul trebuie să figureze DECEDAT în Core Banking
  3. INCOME_CLASSIFIER -> inventarul soldurilor (masa succesorală)
  4. RULE_ENGINE       -> R-SUC-02 împarte DETERMINIST soldul pe cote; R-SUC-03 oprește plata dacă există popriri
  5. ANOMALY           -> plăți din cont și pensii încasate după deces
  6. OUTCOME           -> răspunsul către notar cu suma fiecărui moștenitor

Nimic nu se blochează (`amount_to_hold` = 0): banca nu mai plătește executorii (insolvență)
sau ține soldul până la plata către moștenitori (succesiune).
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import yaml

from app.contracts import (
    AgentName, AgentStatus, BankSnapshot, Case, CaseOutcome, CaseStatus, ClassificationMethod,
    ClassifiedTransaction, CustomerStatus, DocType, ExceptionCode, ExceptionFlag, GarnishmentDecision,
    GarnishmentOrder, IncomeCategory, IssuerType, ModuleInfo, ModuleStatus, ReviewAction, RuleApplication,
    Severity, TxDirection, money,
)
from app.core import llm
from app.core.core_banking import CoreBankingMock
from app.core.events import EmitFn
from app.core.validators import check_consignment_iban, names_match, normalize_text, validate_national_id

ZERO = Decimal("0.00")
RULES_PATH = Path(__file__).parent / "rules" / "v2026_10.yaml"
_SIGNATURE = re.compile(r"semn[ăa]tur[ăa] [șs]i [șs]tampil[ăa]|L\.S\.|semn[ăa]tur[ăa] electronic[ăa]", re.I)
_DATE = r"(\d{2}\.\d{2}\.\d{4})"


@lru_cache
def _rules() -> tuple[str, dict[str, dict]]:
    raw = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    return raw["version"], {r["id"]: r for r in raw["rules"]}


def _apply(rule_id: str, base: Decimal, amount: Decimal, extra: str = "",
           tx_ids: list[str] | None = None) -> RuleApplication:
    rule = _rules()[1][rule_id]
    return RuleApplication(rule_id=rule_id, legal_source=rule["legal_source"],
                           description=rule["description"] + (f" {extra}" if extra else ""),
                           base_amount=money(base), seizable_amount=money(amount), tx_ids=tx_ids or [])


def _parse_date(value: str | None) -> date | None:
    try:
        return datetime.strptime(value, "%d.%m.%Y").date() if value else None
    except ValueError:
        return None


def _flag(code: ExceptionCode, agent: AgentName, message: str, evidence: list[str],
          severity: Severity = Severity.BLOCKING) -> ExceptionFlag:
    return ExceptionFlag(code=code, severity=severity, agent=agent, message=message, evidence=evidence)


# ---------- Succesiune: moștenitori și cote ----------

@dataclass
class Heir:
    name: str
    national_id: str
    quota: Fraction | None                      # None = cotă necitibilă
    quota_text: str
    share: Decimal = ZERO


_HEIR = re.compile(
    r"^\s*\d+[.)]\s*([^,\n]+),\s*CNP[:\s]*(\d{13})[^\n]*?cot[ăa](?:\s+de)?\s*:?\s*"
    r"(\d+\s*/\s*\d+|\d+(?:[.,]\d+)?\s*%)", re.I | re.M)


def parse_quota(text: str) -> Fraction | None:
    """„1/4” -> 1/4, „37,5%” -> 3/8. Cota trebuie să fie în (0, 1]."""
    text = text.replace(" ", "").replace(",", ".")
    try:
        q = Fraction(text[:-1]) / 100 if text.endswith("%") else Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return q if 0 < q <= 1 else None


def split_estate(total: Decimal, heirs: list[Heir]) -> list[Heir]:
    """R-SUC-02: fiecare moștenitor primește `total × cotă`, rotunjit la bani.

    Diferența de rotunjire merge la moștenitorul cu cota cea mai mare (primul, la egalitate),
    ca suma părților să fie EXACT soldul total. Presupune cote valide care însumează 1.
    """
    total = money(max(total, ZERO))
    for h in heirs:
        h.share = money(total * Decimal(h.quota.numerator) / Decimal(h.quota.denominator))
    if heirs:
        biggest = max(heirs, key=lambda h: h.quota)
        biggest.share = money(biggest.share + total - sum((h.share for h in heirs), ZERO))
    return heirs


def _extract_certificate(text: str) -> tuple[GarnishmentOrder, list[Heir], date | None]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    number = re.search(r"CERTIFICAT(?:UL)?\s+DE\s+MO[ȘSŞ]TENITOR\s+nr\.?\s*([0-9A-Z/\-]+)", text, re.I)
    issued = re.search(r"Data:\s*" + _DATE, text, re.I)
    deceased = re.search(r"(?:Defunct(?:ul|a)?|Autorul moștenirii|Autorul mostenirii)[ \t]*:[ \t]*([^,\n]+),\s*CNP[:\s]*(\d+)",
                         text, re.I)
    died = re.search(r"decedat(?:ă|a)?\s+(?:la|în|in)\s+(?:data\s+de\s+)?" + _DATE, text, re.I)
    heirs = [Heir(normalize_text(m.group(1)), m.group(2), parse_quota(m.group(3)), m.group(3).strip())
             for m in _HEIR.finditer(text)]

    order = GarnishmentOrder(
        doc_type=DocType.CERTIFICAT_MOSTENITOR, issuer_name=(lines[0] if lines else "NOTAR PUBLIC")[:120],
        issuer_type=IssuerType.ALTUL, case_number=number.group(1) if number else None,
        issue_date=_parse_date(issued.group(1) if issued else None),
        debtor_name=normalize_text(deceased.group(1)) if deceased else None,
        debtor_id=deceased.group(2) if deceased else None, creditor_name=None,
        has_signature_and_stamp=bool(_SIGNATURE.search(text)), extraction_method="REGEX")

    if not heirs or not order.debtor_id:
        data = llm.chat_json(_CERT_SYSTEM, text[:5000])
        if isinstance(data, dict):
            order.extraction_method = "LLM"
            order.debtor_name = order.debtor_name or normalize_text(str(data.get("deceased_name") or "")) or None
            order.debtor_id = order.debtor_id or re.sub(r"\D", "", str(data.get("deceased_cnp") or "")) or None
            if not heirs:
                heirs = [Heir(normalize_text(str(h.get("name", ""))), re.sub(r"\D", "", str(h.get("cnp", ""))),
                              parse_quota(str(h.get("quota", ""))), str(h.get("quota", "")))
                         for h in data.get("heirs") or [] if isinstance(h, dict)]
    _confidence(order)
    return order, heirs, _parse_date(died.group(1) if died else None)


_CERT_SYSTEM = """Ești un agent juridic al Raiffeisen Bank România. Primești un certificat de moștenitor emis de un notar.
Extrage JSON: {"deceased_name": "NUME PRENUME", "deceased_cnp": "13 cifre",
"heirs": [{"name": "NUME PRENUME", "cnp": "13 cifre", "quota": "1/2"}]}.
Cota o scrii ca fracție (ex. "3/8") sau procent (ex. "37,5%"), exact cum apare în document."""


# ---------- Insolvență ----------

_INS_SYSTEM = """Ești un agent juridic al Raiffeisen Bank România. Primești o notificare privind deschiderea procedurii
insolvenței (Legea 85/2014). Extrage JSON: {"court": "...", "case_number": "...", "debtor_name": "...",
"debtor_id": "CUI fără RO", "practitioner": "administratorul sau lichidatorul judiciar", "opening_date": "DD.MM.YYYY",
"insolvency_iban": "RO..." sau null}."""


@dataclass
class InsolvencyNotice:
    practitioner: str | None
    is_bankruptcy: bool                         # faliment / procedură simplificată -> lichidator
    opening_date: date | None


def _extract_insolvency(text: str) -> tuple[GarnishmentOrder, InsolvencyNotice]:
    norm = normalize_text(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    number = re.search(r"Dosar(?:ul)?\s+nr\.?\s*([0-9A-Z/\-]+)", text, re.I)
    issued = re.search(r"Data:\s*" + _DATE, text, re.I)
    debtor = re.search(r"Debitor(?:ul|ului)?[ \t]*:[ \t]*([^,\n]+),\s*(?:CUI|CIF|CNP|C\.U\.I\.)[:\s]*(?:RO)?\s*(\d+)",
                       text, re.I)
    practitioner = re.search(r"(?:Administrator|Lichidator)(?:ul)?\s+judiciar[ \t]*:[ \t]*([^\n]+)", text, re.I)
    opened = re.search(r"(?:deschiderii procedurii|deschiderea procedurii|deschis[ăa]? procedura)[^\n]*?"
                       r"(?:din|la|:)\s*(?:data\s+de\s+)?" + _DATE, text, re.I)
    iban = re.search(r"(?:cont(?:ul)?\s+(?:unic\s+)?de\s+insolven\w+|IBAN)[^\n:]*:\s*(RO[0-9A-Z ]{20,30})", text, re.I)

    order = GarnishmentOrder(
        doc_type=DocType.NOTIFICARE_INSOLVENTA, issuer_name=(lines[0] if lines else "TRIBUNAL")[:120],
        issuer_type=IssuerType.ALTUL, case_number=number.group(1) if number else None,
        issue_date=_parse_date(issued.group(1) if issued else None),
        debtor_name=normalize_text(debtor.group(1)) if debtor else None,
        debtor_id=debtor.group(2) if debtor else None,
        creditor_name=practitioner.group(1).strip() if practitioner else None,
        consignment_iban=iban.group(1).replace(" ", "").upper() if iban else None,
        has_signature_and_stamp=bool(_SIGNATURE.search(text)), extraction_method="REGEX")
    notice = InsolvencyNotice(
        practitioner=order.creditor_name,
        is_bankruptcy="FALIMENT" in norm or "SIMPLIFICAT" in norm or "LICHIDATOR" in norm,
        opening_date=_parse_date(opened.group(1) if opened else None))

    if not (order.case_number and order.debtor_id):
        data = llm.chat_json(_INS_SYSTEM, text[:5000])
        if isinstance(data, dict):
            order.extraction_method = "LLM"
            order.case_number = order.case_number or data.get("case_number")
            order.debtor_name = order.debtor_name or normalize_text(str(data.get("debtor_name") or "")) or None
            order.debtor_id = order.debtor_id or re.sub(r"\D", "", str(data.get("debtor_id") or "")) or None
            order.creditor_name = notice.practitioner = order.creditor_name or data.get("practitioner")
            notice.opening_date = notice.opening_date or _parse_date(data.get("opening_date"))
    _confidence(order)
    return order, notice


def _confidence(order: GarnishmentOrder) -> None:
    order.field_confidence = {f: (0.97 if getattr(order, f) not in (None, "") else 0.0)
                              for f in ("issuer_name", "case_number", "issue_date", "debtor_name", "debtor_id")}


# ---------- Modulul ----------

class InsolventaModule:
    info = ModuleInfo(
        module_id="insolventa",
        name="Insolvență și succesiuni",
        description="Notificări de deschidere a procedurii de insolvență (Legea 85/2014) și certificate de "
                    "moștenitor: suspendarea popririlor și împărțirea soldului pe moștenitori.",
        status=ModuleStatus.ACTIVE,
        handled_doc_types=[DocType.NOTIFICARE_INSOLVENTA, DocType.CERTIFICAT_MOSTENITOR],
    )

    def process(self, case: Case, bank: BankSnapshot, emit: EmitFn,
                review: ReviewAction | None = None) -> Case:
        if case.doc_type == DocType.CERTIFICAT_MOSTENITOR:
            return _Succession(case, bank, emit, review).run()
        return _Insolvency(case, bank, emit, review).run()


class _Pipeline:
    """Pașii comuni: identificarea clientului, inventarul soldurilor, finalizarea dosarului."""
    letter_target = ""

    def __init__(self, case: Case, bank: BankSnapshot, emit: EmitFn, review: ReviewAction | None):
        self.case, self.emit, self.review = case, emit, review
        self.core = CoreBankingMock(bank)
        self.exceptions: list[ExceptionFlag] = []
        self.order: GarnishmentOrder | None = None
        self.customer = None
        self.accounts: list = []
        self.transactions: list = []
        self.garnishments: list = []
        self.positions: list[ClassifiedTransaction] = []
        self.decision: GarnishmentDecision | None = None

    def flag(self, *args, **kwargs) -> None:
        self.exceptions.append(_flag(*args, **kwargs))

    def check_document(self, required: dict[str, str]) -> None:
        missing = [label for field, label in required.items() if not getattr(self.order, field)]
        if missing:
            self.flag(ExceptionCode.E05_DOCUMENT_INVALID, AgentName.EXTRACTION,
                      "Câmpuri obligatorii lipsă în document: " + ", ".join(missing), missing)
        if not self.order.has_signature_and_stamp:
            self.flag(ExceptionCode.E05_DOCUMENT_INVALID, AgentName.EXTRACTION,
                      "Documentul nu poartă semnătură și ștampilă.", ["has_signature_and_stamp"])
        if self.order.debtor_id and not validate_national_id(self.order.debtor_id):
            self.flag(ExceptionCode.E01_IDENTITATE, AgentName.EXTRACTION,
                      f"CNP/CUI-ul {self.order.debtor_id} este invalid (cifra de control nu corespunde).", ["debtor_id"])

    def identify(self, not_found: ExceptionFlag | None) -> bool:
        """Caută clientul. False = nu continuăm (identitate invalidă sau client inexistent)."""
        self.emit(AgentName.RECONCILIATION, AgentStatus.STARTED, "Caut titularul și conturile lui în Core Banking", {})
        if any(e.code == ExceptionCode.E01_IDENTITATE and e.evidence == ["debtor_id"] for e in self.exceptions):
            return self._stop("CNP/CUI invalid: căutarea în Core Banking a fost oprită")
        self.customer = self.core.find_customer(self.order.debtor_id) if self.order.debtor_id else None
        if self.customer is None:
            if not_found:
                self.exceptions.append(not_found)
            return self._stop(f"{self.order.debtor_name or 'Titularul'} nu este client al băncii")
        if not names_match(self.customer.full_name, self.order.debtor_name):
            self.flag(ExceptionCode.E01_IDENTITATE, AgentName.RECONCILIATION,
                      f"Numele din document ({self.order.debtor_name}) nu corespunde titularului CNP/CUI-ului "
                      f"din bancă ({self.customer.full_name}).", ["debtor_name"])
        cid = self.customer.customer_id
        self.accounts = self.core.get_accounts(cid)
        self.transactions = self.core.get_transactions(cid)
        self.garnishments = self.core.get_active_garnishments(cid)
        self.emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED,
                  f"Client identificat: {self.customer.full_name} ({self.customer.status.value}) · "
                  f"{len(self.accounts)} conturi · {len(self.garnishments)} popriri active",
                  {"customer_id": cid, "status": self.customer.status.value, "accounts": len(self.accounts),
                   "active_garnishments": len(self.garnishments)})
        return True

    def _stop(self, message: str) -> bool:
        self.emit(AgentName.RECONCILIATION, AgentStatus.COMPLETED, message, {})
        for agent in (AgentName.INCOME_CLASSIFIER, AgentName.RULE_ENGINE, AgentName.ANOMALY):
            self.emit(agent, AgentStatus.SKIPPED, "Nu există conturi de analizat", {"skipped": True})
        return False

    def inventory(self, purpose: str) -> Decimal:
        """Soldurile conturilor (în RON) ca poziții afișabile în UI. Întoarce totalul pozitiv."""
        self.emit(AgentName.INCOME_CLASSIFIER, AgentStatus.STARTED, f"Inventariez soldurile ({purpose})", {})
        ref = self.order.issue_date or self.case.document.received_at.date()
        for acc in self.accounts:
            if acc.current_balance > 0:
                self.positions.append(ClassifiedTransaction(
                    tx_id=f"SOLD-{acc.iban[-6:]}", iban=acc.iban, booking_date=ref, amount=acc.current_balance,
                    counterparty_name="—", description=f"Sold cont {acc.account_type.value}",
                    category=IncomeCategory.SOLD_ANTERIOR, method=ClassificationMethod.PATTERN, confidence=1.0,
                    rationale=f"Soldul intră în {purpose}."))
        total = money(sum((p.amount for p in self.positions), ZERO))
        self.emit(AgentName.INCOME_CLASSIFIER, AgentStatus.COMPLETED,
                  f"{len(self.positions)} solduri pozitive · total {total} RON", {"total_balance": float(total)})
        return total

    def debits_after(self, when: date | None) -> list:
        return [t for t in self.transactions if when and t.direction == TxDirection.DEBIT and t.booking_date > when]

    def finish(self, letter_builder, auto_summary: str) -> Case:
        self.emit(AgentName.OUTCOME, AgentStatus.STARTED, f"Redactez răspunsul către {self.letter_target}", {})
        resolved = set(self.review.resolve_codes) if self.review else set()
        final = [e.model_copy(update={"resolved": True, "resolution_note": self.review.note})
                 if e.code.value in resolved else e for e in self.exceptions]
        blocking = sorted({e.code.value for e in final if e.severity == Severity.BLOCKING and not e.resolved})
        if blocking:
            status, letter = CaseStatus.EXCEPTION_FLAGGED, None
            summary = (f"Documentul {self.order.case_number or 'fără număr'} așteaptă decizia ofițerului: "
                       f"excepții blocante {', '.join(blocking)}. Nu s-a transmis niciun răspuns.")
        else:
            status, letter, summary = CaseStatus.AUTO_PROCESSED, letter_builder(), auto_summary
        self.emit(AgentName.OUTCOME, AgentStatus.COMPLETED, f"Rezultat: {status.value}",
                  {"status": status.value, "summary": summary})
        return self.case.model_copy(update={
            "order": self.order, "customer": self.customer, "accounts": self.accounts,
            "active_garnishments": self.garnishments, "classified_transactions": self.positions,
            "decision": self.decision, "exceptions": final, "status": status,
            "outcome": CaseOutcome(status=status, summary=summary, response_letter_text=letter),
        })

    def _decision(self, total: Decimal, rules: list[RuleApplication]) -> GarnishmentDecision:
        return GarnishmentDecision(exempt_total=total, amount_to_hold=ZERO, amount_protected=total,
                                   rules_applied=rules, rules_version=_rules()[0])

    def _letter_head(self, ref: str) -> list[str]:
        return ["RAIFFEISEN BANK S.A. — Departamentul Operațiuni Juridice",
                f"Data: {date.today():%d.%m.%Y}", f"Către: {self.letter_target}", f"Ref.: {ref}", ""]


class _Insolvency(_Pipeline):
    def run(self) -> Case:
        self.emit(AgentName.EXTRACTION, AgentStatus.STARTED, "Extrag datele din notificarea de insolvență", {})
        self.order, self.notice = _extract_insolvency(self.case.document.text or "")
        self.letter_target = self.notice.practitioner or self.order.issuer_name
        self.check_document({"case_number": "nr. dosar", "debtor_name": "debitor", "debtor_id": "CUI debitor",
                             "creditor_name": "administrator / lichidator judiciar"})
        if self.order.debtor_id and len(self.order.debtor_id) == 13:
            self.flag(ExceptionCode.E08_STATUT_CLIENT, AgentName.EXTRACTION,
                      "Debitorul are CNP (persoană fizică): Legea 85/2014 se aplică profesioniștilor; "
                      "verificați dacă este o procedură de insolvență a persoanei fizice.", ["debtor_id"],
                      Severity.WARNING)
        if self.order.consignment_iban:
            iban = check_consignment_iban(self.order.consignment_iban)
            if not iban.ok:
                self.flag(ExceptionCode.E09_IBAN_CONSEMNARE, AgentName.EXTRACTION,
                          iban.reason.replace("de consemnare", "de insolvență"), ["consignment_iban"], Severity.WARNING)
        self.emit(AgentName.EXTRACTION, AgentStatus.COMPLETED,
                  f"Dosar {self.order.case_number} · debitor {self.order.debtor_name} · "
                  f"{'lichidator' if self.notice.is_bankruptcy else 'administrator'} judiciar: {self.notice.practitioner}",
                  {"order": self.order.model_dump(mode="json"),
                   "opening_date": self.notice.opening_date.isoformat() if self.notice.opening_date else None})

        if not self.identify(not_found=None):
            return self.finish(self._letter_not_client, f"{self.order.debtor_name} nu este client: s-a răspuns "
                                                        f"{self.letter_target} că banca nu deține conturi ale debitorului.")
        if self.customer.status == CustomerStatus.INSOLVENTA:
            self.flag(ExceptionCode.E02_DUPLICAT, AgentName.RECONCILIATION,
                      "Clientul figurează deja în insolvență: notificarea pare deja înregistrată.",
                      [self.customer.customer_id], Severity.WARNING)
        elif self.customer.status == CustomerStatus.DECEDAT:
            self.flag(ExceptionCode.E08_STATUT_CLIENT, AgentName.RECONCILIATION,
                      "Debitorul figurează DECEDAT în Core Banking: o procedură de insolvență nu se potrivește.",
                      [self.customer.customer_id])

        total = self.inventory("averea debitorului aflat în insolvență")

        self.emit(AgentName.RULE_ENGINE, AgentStatus.STARTED, "Aplic regulile Legii 85/2014", {})
        rules = [_apply("R-INS-01", max(g.total_due - g.amount_recovered, ZERO), ZERO,
                        f"Poprire suspendată: dosar {g.case_number} ({g.creditor_name}).")
                 for g in self.garnishments]
        rules.append(_apply("R-INS-02", total, ZERO,
                            f"{len(self.accounts)} conturi marcate INSOLVENTA.", [p.tx_id for p in self.positions]))
        self.decision = self._decision(total, rules)
        self.emit(AgentName.RULE_ENGINE, AgentStatus.COMPLETED,
                  f"{len(self.garnishments)} popriri suspendate · {len(self.accounts)} conturi marcate INSOLVENTA",
                  {"suspended": [g.case_number for g in self.garnishments]})

        self.emit(AgentName.ANOMALY, AgentStatus.STARTED, "Caut plăți ieșite după deschiderea procedurii", {})
        late = self.debits_after(self.notice.opening_date)
        if late:
            self.flag(ExceptionCode.E06_SUSPICIUNE_ELUDARE, AgentName.ANOMALY,
                      f"{len(late)} plăți ({money(sum((t.amount for t in late), ZERO))} RON) după deschiderea procedurii "
                      f"({self.notice.opening_date:%d.%m.%Y}): pot fi nule (Legea 85/2014, art. 84). "
                      "Se comunică administratorului / lichidatorului judiciar.",
                      [t.tx_id for t in late], Severity.WARNING)
        self.emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
                  f"{len(late)} plăți după deschiderea procedurii" if late else "Nicio plată după deschiderea procedurii",
                  {"late_debits": [t.tx_id for t in late]})

        return self.finish(lambda: self._letter_client(late),
                           f"Insolvență înregistrată pentru {self.customer.full_name}: {len(self.garnishments)} popriri "
                           f"suspendate, {len(self.accounts)} conturi (sold {money(total)} RON) marcate INSOLVENTA.")

    def _letter_not_client(self) -> str:
        return "\n".join(self._letter_head(f"Dosar nr. {self.order.case_number}") + [
            f"Urmare a notificării privind deschiderea procedurii insolvenței debitorului {self.order.debtor_name} "
            f"(CUI {self.order.debtor_id}), vă comunicăm că acesta nu figurează în evidențele Raiffeisen Bank S.A. "
            "și nu deține conturi deschise la bancă.", "", "Cu stimă,", "Raiffeisen Bank S.A."])

    def _letter_client(self, late: list) -> str:
        accs = [f"  • {a.iban} ({a.account_type.value}): sold {money(a.current_balance)} RON" for a in self.accounts] \
            or ["  • Debitorul nu are conturi active."]
        susp = [f"  • dosar {g.case_number}, {g.issuer_name} (creditor {g.creditor_name})" for g in self.garnishments] \
            or ["  • Nu existau popriri active."]
        lines = self._letter_head(f"Dosar nr. {self.order.case_number} — {self.order.issuer_name}") + [
            f"Am luat act de deschiderea procedurii insolvenței debitorului {self.order.debtor_name} "
            f"(CUI {self.order.debtor_id}). În temeiul Legii nr. 85/2014:", "",
            "1. Conturile debitorului au fost marcate în evidențele băncii:", *accs, "",
            "2. Popririle active au fost suspendate (art. 75 alin. (1)) și nu se mai virează sume executorilor:", *susp, ""]
        if late:
            lines += [f"3. După data deschiderii procedurii au fost efectuate {len(late)} plăți din cont, în total "
                      f"{money(sum((t.amount for t in late), ZERO))} RON (detaliile sunt anexate).", ""]
        return "\n".join(lines + ["Operațiunile ulterioare se efectuează numai cu acordul dumneavoastră.",
                                  "", "Cu stimă,", "Raiffeisen Bank S.A."])


class _Succession(_Pipeline):
    def run(self) -> Case:
        self.emit(AgentName.EXTRACTION, AgentStatus.STARTED, "Extrag defunctul și moștenitorii din certificat", {})
        self.order, self.heirs, self.death_date = _extract_certificate(self.case.document.text or "")
        self.letter_target = self.order.issuer_name
        self.check_document({"case_number": "nr. certificat", "debtor_name": "defunct", "debtor_id": "CNP defunct"})
        self._check_heirs()
        self.emit(AgentName.EXTRACTION, AgentStatus.COMPLETED,
                  f"Certificat {self.order.case_number} · defunct {self.order.debtor_name} · "
                  f"{len(self.heirs)} moștenitori ({', '.join(h.quota_text for h in self.heirs)})",
                  {"order": self.order.model_dump(mode="json"),
                   "heirs": [{"name": h.name, "cnp": h.national_id, "quota": h.quota_text} for h in self.heirs]})

        not_found = _flag(ExceptionCode.E01_IDENTITATE, AgentName.RECONCILIATION,
                          f"Defunctul {self.order.debtor_name} ({self.order.debtor_id}) nu este client al băncii.",
                          ["debtor_id"])
        if not self.identify(not_found):    # E01 blocant: răspunsul îl redactează ofițerul
            return self.finish(lambda: None, f"Defunctul {self.order.debtor_name} nu are conturi la bancă.")
        if self.customer.status != CustomerStatus.DECEDAT:
            self.flag(ExceptionCode.E08_STATUT_CLIENT, AgentName.RECONCILIATION,
                      f"Titularul figurează {self.customer.status.value} în Core Banking, nu DECEDAT: "
                      "verificați certificatul de deces înainte de orice plată.", [self.customer.customer_id])

        total = self.inventory("masa succesorală")

        self.emit(AgentName.RULE_ENGINE, AgentStatus.STARTED, "Împart soldul pe cotele din certificat", {})
        rules = [_apply("R-SUC-01", total, total)]
        self.valid = valid = not any(e.evidence and e.evidence[0] in ("heirs", "quota") for e in self.exceptions)
        if valid:
            split_estate(total, self.heirs)
            rules += [_apply("R-SUC-02", total, h.share, f"Moștenitor {h.name} (CNP {h.national_id}), cotă {h.quota_text}.")
                      for h in self.heirs]
        if self.garnishments:
            due = sum((max(g.total_due - g.amount_recovered, ZERO) for g in self.garnishments), ZERO)
            rules.append(_apply("R-SUC-03", total, ZERO, f"Popriri active pe defunct: {money(due)} RON."))
            self.flag(ExceptionCode.E04_POPRIRI_CONCURENTE, AgentName.RULE_ENGINE,
                      f"Pe defunct există {len(self.garnishments)} popriri active ({money(due)} RON): datoriile trec la "
                      "moștenitori proporțional cu cota (Codul civil, art. 1155). Ofițerul decide înainte de plată.",
                      [g.case_number for g in self.garnishments])
        self.decision = self._decision(total, rules)
        self.emit(AgentName.RULE_ENGINE, AgentStatus.COMPLETED,
                  " · ".join(f"{h.name}: {h.share} RON" for h in self.heirs) if valid else "Cote invalide: împărțire oprită",
                  {"shares": {h.name: float(h.share) for h in self.heirs} if valid else {}})

        self.emit(AgentName.ANOMALY, AgentStatus.STARTED, "Caut operațiuni după data decesului", {})
        late = self.debits_after(self.death_date)
        pensions = [t for t in self.transactions if self.death_date and t.direction == TxDirection.CREDIT
                    and t.booking_date > self.death_date and "PENSI" in normalize_text(t.counterparty_name + t.description)]
        if late:
            self.flag(ExceptionCode.E06_SUSPICIUNE_ELUDARE, AgentName.ANOMALY,
                      f"{len(late)} plăți din cont ({money(sum((t.amount for t in late), ZERO))} RON) după deces "
                      f"({self.death_date:%d.%m.%Y}): cineva a folosit contul sau cardul defunctului.",
                      [t.tx_id for t in late], Severity.WARNING)
        if pensions:
            self.flag(ExceptionCode.E06_SUSPICIUNE_ELUDARE, AgentName.ANOMALY,
                      f"Pensie încasată după deces ({money(sum((t.amount for t in pensions), ZERO))} RON): "
                      "se returnează casei de pensii, nu intră în masa succesorală.",
                      [t.tx_id for t in pensions], Severity.WARNING)
        self.emit(AgentName.ANOMALY, AgentStatus.COMPLETED,
                  f"{len(late)} plăți și {len(pensions)} pensii după deces" if late or pensions
                  else "Nicio operațiune după deces", {"late_debits": len(late), "late_pensions": len(pensions)})

        return self.finish(self._letter, f"Succesiunea lui {self.customer.full_name}: soldul de {money(total)} RON "
                                         f"se împarte la {len(self.heirs)} moștenitori conform certificatului "
                                         f"{self.order.case_number}.")

    def _check_heirs(self) -> None:
        if not self.heirs:
            self.flag(ExceptionCode.E05_DOCUMENT_INVALID, AgentName.EXTRACTION,
                      "Nu am găsit moștenitorii și cotele lor în certificat.", ["heirs"])
            return
        for h in self.heirs:
            if not validate_national_id(h.national_id):
                self.flag(ExceptionCode.E01_IDENTITATE, AgentName.EXTRACTION,
                          f"CNP-ul moștenitorului {h.name} ({h.national_id}) este invalid.", ["heirs", h.national_id])
        bad = [h.quota_text for h in self.heirs if h.quota is None]
        if bad:
            self.flag(ExceptionCode.E05_DOCUMENT_INVALID, AgentName.EXTRACTION,
                      f"Cote necitibile în certificat: {', '.join(bad)}.", ["quota"])
        elif (s := sum((h.quota for h in self.heirs), Fraction(0))) != 1:
            self.flag(ExceptionCode.E05_DOCUMENT_INVALID, AgentName.EXTRACTION,
                      f"Cotele moștenitorilor însumează {s} ({float(s):.2%}), nu 1 (100%).", ["quota"])

    def _letter(self) -> str:
        if not self.valid:                  # ofițerul a închis dosarul, dar cotele nu permit plata
            return "\n".join(self._letter_head(f"Certificat de moștenitor nr. {self.order.case_number}") + [
                f"Moștenitorii sau cotele din certificatul privind succesiunea defunctului {self.order.debtor_name} "
                "nu pot fi verificate. Vă rugăm să ne transmiteți certificatul rectificat; până atunci nu se "
                "eliberează nicio sumă.", "", "Cu stimă,", "Raiffeisen Bank S.A."])
        rows = [f"  • {h.name} (CNP {h.national_id}), cotă {h.quota_text}: {h.share} RON" for h in self.heirs]
        return "\n".join(self._letter_head(f"Certificat de moștenitor nr. {self.order.case_number}") + [
            f"Urmare a certificatului de moștenitor privind succesiunea defunctului {self.order.debtor_name} "
            f"(CNP {self.order.debtor_id}), vă comunicăm că soldul total al conturilor deschise la Raiffeisen Bank S.A. "
            f"este de {self.decision.amount_protected} RON și se împarte între moștenitori astfel "
            "(Codul civil, art. 1132–1133):", "", *rows, "",
            "Sumele se eliberează fiecărui moștenitor la prezentarea actului de identitate, "
            "sau în contul indicat de acesta.", "", "Cu stimă,", "Raiffeisen Bank S.A."])
