"""Agentul 1: Extragere și triaj juridic. Proprietar: Om1.

Strategie: LLM (Featherless) cu schemă JSON -> dacă eșuează, parser regex (șabloanele Om3).
Apoi validare deterministă: CNP/CUI, IBAN, sume, semnătură.
"""
import re
from datetime import datetime
from decimal import Decimal

from app import config
from app.contracts import (AgentName, AgentStatus, CreditorType, DocType, ExceptionCode, ExceptionFlag,
                           GarnishmentOrder, IssuerType, Severity, money)
from app.core import llm
from app.core.validators import normalize_text, validate_iban, validate_national_id
from .context import AgentContext

CRITICAL_FIELDS = ["case_number", "debtor_name", "debtor_id", "total_due"]

_SYSTEM = """Extragi date dintr-o adresă de poprire trimisă unei bănci din România.
Întoarce un obiect JSON cu cheile:
doc_type (POPRIRE_INFIINTARE|POPRIRE_SISTARE|POPRIRE_MODIFICARE|CERERE_INFORMATII),
issuer_name, issuer_type (EXECUTOR|ANAF|ORGAN_FISCAL_LOCAL|ALTUL), case_number,
issue_date (YYYY-MM-DD), debtor_name (MAJUSCULE), debtor_id (CNP sau CUI, doar cifre),
creditor_name, creditor_type (INTRETINERE|FISCAL|COMERCIAL),
principal, enforcement_costs, total_due (numere, fără separator de mii),
consignment_iban (fără spații), has_signature_and_stamp (bool),
references_case_number (la sistare/modificare: dosarul vizat, altfel null),
field_confidence (obiect: încrederea 0-1 pentru fiecare cheie de mai sus).
Dacă un câmp lipsește, pune null și încredere 0. Nu inventa."""


# ---------- parser regex (fallback determinist) ----------

def _ro_amount(value: str | None) -> Decimal:
    if not value:
        return Decimal(0)
    return money(value.replace(".", "").replace(" ", "").replace(",", "."))


def _find(pattern: str, text: str, flags=re.I) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def parse_with_regex(text: str, doc_type: DocType) -> GarnishmentOrder:
    norm = normalize_text(text)
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if "ADMINISTRARE FISCALA" in norm or "ANAF" in norm.split("\n")[0]:
        issuer_type, default_creditor = IssuerType.ANAF, CreditorType.FISCAL
    elif "EXECUTOR" in normalize_text(first_line) or "EXECUTORULUI" in norm:
        issuer_type, default_creditor = IssuerType.EXECUTOR, CreditorType.COMERCIAL
    else:
        issuer_type, default_creditor = IssuerType.ALTUL, CreditorType.COMERCIAL

    nature = normalize_text(_find(r"Natura crean[țt]ei:\s*(.+)", text))
    if "INTRETINERE" in nature or "ALIMENTAR" in nature:
        creditor_type = CreditorType.INTRETINERE
    elif "FISCAL" in nature:
        creditor_type = CreditorType.FISCAL
    elif nature:
        creditor_type = CreditorType.COMERCIAL
    else:
        creditor_type = default_creditor

    debtor = re.search(r"Debitor:\s*([^,\n]+),\s*(?:CNP|CUI|CIF)[:\s]*([0-9]+)", text, re.I)
    date_s = _find(r"Data:\s*(\d{2}\.\d{2}\.\d{4})", text)
    iban = _find(r"IBAN[:\s]*(RO[0-9A-Z ]{22,30})", text)
    iban = re.sub(r"\s", "", iban)[:24] if iban else None
    principal = _ro_amount(_find(r"Debit principal:\s*([\d\.\s]+,\d{2})", text))
    costs = _ro_amount(_find(r"Cheltuieli de executare:\s*([\d\.\s]+,\d{2})", text))
    total = _ro_amount(_find(r"Total de recuperat:\s*([\d\.\s]+,\d{2})", text))
    case_no = _find(r"[Dd]osar(?:ul)? de executare (?:nr\.?)\s*([0-9]+/[0-9]{4}(?:/[A-Z0-9]+)?)", text)
    ref = _find(r"(?:înființată|infiintata|instituită|instituita)[^\n]*?dosarul de executare nr\.?\s*([0-9]+/[0-9]{4})", text)

    order = GarnishmentOrder(
        doc_type=doc_type, issuer_name=first_line[:120], issuer_type=issuer_type,
        case_number=case_no,
        issue_date=datetime.strptime(date_s, "%d.%m.%Y").date() if date_s else None,
        debtor_name=normalize_text(debtor.group(1)) if debtor else None,
        debtor_id=debtor.group(2) if debtor else None,
        creditor_name=_find(r"Creditor:\s*(.+)", text),
        creditor_type=creditor_type,
        principal=principal, enforcement_costs=costs, total_due=total,
        consignment_iban=iban,
        has_signature_and_stamp=bool(re.search(r"semn[ăa]tur[ăa] [șs]i [șs]tampil[ăa]|L\.S\.", text, re.I)),
        references_case_number=ref, extraction_method="REGEX",
    )
    order.field_confidence = {f: (0.9 if getattr(order, f) not in (None, "", Decimal(0)) else 0.0)
                              for f in GarnishmentOrder.model_fields if f not in ("field_confidence", "extraction_method")}
    return order


def _parse_with_llm(text: str, doc_type: DocType) -> GarnishmentOrder | None:
    data = llm.chat_json(_SYSTEM, text[:6000])
    if not isinstance(data, dict):
        return None
    try:
        data.setdefault("doc_type", doc_type.value)
        data["extraction_method"] = "LLM"
        data = {k: v for k, v in data.items() if k in GarnishmentOrder.model_fields}
        return GarnishmentOrder.model_validate(data)
    except Exception:
        return None


# ---------- agentul ----------

def run(state: dict, ctx: AgentContext) -> dict:
    emit = ctx.emit
    doc = state["document"]
    doc_type = state.get("doc_type_hint") or DocType.POPRIRE_INFIINTARE
    emit(AgentName.EXTRACTION, AgentStatus.STARTED, "Extrag datele din adresa de poprire", {})

    order = _parse_with_llm(doc.text or "", doc_type) or parse_with_regex(doc.text or "", doc_type)
    order.doc_type = doc_type  # tipul stabilit de router are prioritate
    exceptions: list[ExceptionFlag] = []

    # validări deterministe
    missing = [f for f in CRITICAL_FIELDS
               if getattr(order, f) in (None, "", Decimal(0)) and not (f == "total_due" and doc_type == DocType.POPRIRE_SISTARE)]
    low = [f for f in CRITICAL_FIELDS
           if f not in missing and order.field_confidence.get(f, 1.0) < config.MIN_FIELD_CONFIDENCE]
    if missing or low:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message="Câmpuri critice lipsă sau citite cu încredere scăzută: " + ", ".join(missing + low),
            evidence=missing + low))
    if not order.has_signature_and_stamp:
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message="Adresa nu pare semnată și ștampilată de emitent.", evidence=["has_signature_and_stamp"]))
    if order.debtor_id and not validate_national_id(order.debtor_id):
        exceptions.append(ExceptionFlag(
            code=ExceptionCode.E01_IDENTITATE, severity=Severity.BLOCKING, agent=AgentName.EXTRACTION,
            message=f"CNP/CUI-ul debitorului ({order.debtor_id}) nu este valid (cifra de control nu corespunde).",
            evidence=["debtor_id"]))
    if doc_type != DocType.POPRIRE_SISTARE:
        if order.principal + order.enforcement_costs != order.total_due and order.principal > 0:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E05_DOCUMENT_INVALID, severity=Severity.WARNING, agent=AgentName.EXTRACTION,
                message=f"Debit principal + cheltuieli ({order.principal} + {order.enforcement_costs}) "
                        f"≠ total ({order.total_due}).", evidence=["total_due"]))
        if not validate_iban(order.consignment_iban):
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E09_IBAN_CONSEMNARE, severity=Severity.WARNING, agent=AgentName.EXTRACTION,
                message=f"IBAN-ul de consemnare ({order.consignment_iban}) lipsește sau este invalid.",
                evidence=["consignment_iban"]))

    emit(AgentName.EXTRACTION, AgentStatus.COMPLETED,
         f"Dosar {order.case_number}, debitor {order.debtor_name}, total {order.total_due} RON",
         {"order": order.model_dump(mode="json"), "exceptions": [e.code.value for e in exceptions]})
    return {"order": order, "exceptions": exceptions}
