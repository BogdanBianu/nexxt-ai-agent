"""Agentul 1: Extragere și triaj juridic. Proprietar: Om1.

Strategie: LLM (AWS Bedrock) cu schemă JSON -> dacă eșuează, parser regex (șabloanele Om3).
Apoi validare deterministă matematică: CNP/CUI (cifră de control), IBAN (ISO 7064 mod 97), sume, semnătură.
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

_SYSTEM = """Ești un agent AI specializat în extragerea datelor juridice din adresele de poprire (Art. 781 Cod Procedură Civilă) primite de Raiffeisen Bank România.
Extrage cu maximă precizie câmpurile din document și întoarce UN OBIECT JSON cu exact următoarele chei:
- doc_type: "POPRIRE_INFIINTARE" | "POPRIRE_SISTARE" | "POPRIRE_MODIFICARE" | "CERERE_INFORMATII"
- issuer_name: numele complet al Biroului Executorului Judecătoresc (BEJ) sau al organului fiscal (ANAF)
- issuer_type: "EXECUTOR" | "ANAF" | "ORGAN_FISCAL_LOCAL" | "ALTUL"
- case_number: numărul dosarului de executare (ex: "1234/2026")
- issue_date: data emiterii în format "YYYY-MM-DD" (ex: "25.10.2026" -> "2026-10-25")
- debtor_name: numele debitorului cu MAJUSCULE și FĂRĂ diacritice (ex: "IONESCU MIHAI")
- debtor_id: CNP-ul (13 cifre) sau CUI-ul debitorului (doar cifre, fără spații sau prefix RO)
- creditor_name: numele creditorului urmăritor
- creditor_type:
    * "INTRETINERE" dacă natura creanței este pensie de întreținere / pensie alimentară / obligație legală de întreținere (cota legală 1/2 conform Art. 729 alin. 1 lit. a CPC)
    * "FISCAL" dacă este creanță bugetară / fiscală / ANAF / taxe și impozite
    * "COMERCIAL" pentru orice alte creanțe (credite bancare, leasing, IFN, facturi comerciale — cota legală 1/3 conform Art. 729 alin. 1 lit. b CPC)
- principal: debitul principal ca număr zecimal cu punct (ex: 14000.00; dacă nu e defalcat, 0)
- enforcement_costs: cheltuieli de executare ca număr zecimal cu punct (ex: 1000.00; dacă nu e defalcat, 0)
- total_due: suma totală de recuperat ca număr zecimal cu punct (ex: 15000.00; la sistare pune 0)
- consignment_iban: codul IBAN de consemnare în care banca trebuie să vireze sumele (fără spații, ex: "RO49AAAA1B31007593840000")
- has_signature_and_stamp: true dacă documentul menționează semnătura și ștampila / "L.S." / semnătură electronică calificată, altfel false
- references_case_number: doar la POPRIRE_SISTARE sau POPRIRE_MODIFICARE, numărul dosarului de executare vizat (ex: "7700/2026"), altfel null
- field_confidence: obiect JSON cu scoruri de încredere între 0.0 și 1.0 pentru fiecare câmp extras (ex: {"case_number": 0.99, "debtor_name": 0.99, "debtor_id": 0.99, "total_due": 0.99}).

Reguli stricte:
1. Nu rotunji și nu modifica nicio cifră din CNP, IBAN sau sume!
2. La sume românești (ex. "15.000,00 RON"), punctul este separator de mii și virgula este separator zecimal -> convertește în 15000.00.
3. Dacă un câmp lipsește din text, pune null (sau 0 la sume) și încredere 0.0 în field_confidence."""


# ---------- parser regex (fallback determinist) ----------

def _ro_amount(value: str | None) -> Decimal:
    if not value:
        return Decimal(0)
    cleaned = value.strip().replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return money(cleaned)


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
    if "INTRETINERE" in nature or "ALIMENTAR" in nature or "PENSIE DE INTRETINERE" in norm:
        creditor_type = CreditorType.INTRETINERE
    elif "FISCAL" in nature or "BUGETAR" in nature:
        creditor_type = CreditorType.FISCAL
    elif nature:
        creditor_type = CreditorType.COMERCIAL
    else:
        creditor_type = default_creditor

    debtor = re.search(r"Debitor:\s*([^,\n]+),\s*(?:CNP|C\.N\.P\.|CUI|CIF)[:\s]*([0-9]+)", text, re.I)
    date_s = _find(r"Data:\s*(\d{2}\.\d{2}\.\d{4})", text)
    iban = _find(r"IBAN[:\s]*(RO[0-9A-Z ]{22,30})", text)
    iban = re.sub(r"\s", "", iban)[:24] if iban else None
    principal = _ro_amount(_find(r"Debit principal:\s*([\d\.\s]+,\d{2})", text))
    costs = _ro_amount(_find(r"Cheltuieli de executare:\s*([\d\.\s]+,\d{2})", text))
    total = _ro_amount(_find(r"(?:Total de recuperat|Suma total[ăa]|Total debit):\s*([\d\.\s]+,\d{2})", text))
    case_no = _find(r"[Dd]osar(?:ul)? (?:de executare|execu[țt]ional) (?:nr\.?)\s*([0-9]+/[0-9]{4}(?:/[A-Z0-9]+)?)", text)
    ref = _find(r"(?:înființată|infiintata|instituită|instituita|privind)[^\n]*?dosar(?:ul)? (?:de executare )?nr\.?\s*([0-9]+/[0-9]{4})", text)

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
        has_signature_and_stamp=bool(re.search(r"semn[ăa]tur[ăa] [șs]i [șs]tampil[ăa]|L\.S\.|semn[ăa]tur[ăa] electronic[ăa]", text, re.I)),
        references_case_number=ref or (case_no if doc_type == DocType.POPRIRE_SISTARE else None),
        extraction_method="REGEX",
    )
    order.field_confidence = {f: (0.95 if getattr(order, f) not in (None, "", Decimal(0)) else 0.0)
                              for f in GarnishmentOrder.model_fields if f not in ("field_confidence", "extraction_method")}
    return order


def _parse_with_llm(text: str, doc_type: DocType, fallback_regex: GarnishmentOrder) -> GarnishmentOrder | None:
    data = llm.chat_json(_SYSTEM, text[:6000])
    if not isinstance(data, dict):
        return None
    try:
        data["doc_type"] = doc_type.value
        data["extraction_method"] = "LLM"
        if data.get("debtor_name"):
            data["debtor_name"] = normalize_text(str(data["debtor_name"]))
        if data.get("debtor_id"):
            data["debtor_id"] = re.sub(r"\D", "", str(data["debtor_id"]))
        if data.get("consignment_iban"):
            data["consignment_iban"] = re.sub(r"\s+", "", str(data["consignment_iban"])).upper()[:24]

        # Asigură că field_confidence are cel puțin 0.92 pentru câmpurile extrase clar
        raw_conf = data.get("field_confidence") if isinstance(data.get("field_confidence"), dict) else {}
        clean_data = {k: v for k, v in data.items() if k in GarnishmentOrder.model_fields and v is not None}
        order = GarnishmentOrder.model_validate(clean_data)

        # Completează din fallback-ul regex dacă un câmp critic a fost omis accidental de LLM
        for f in ("case_number", "debtor_name", "debtor_id", "consignment_iban", "references_case_number"):
            if not getattr(order, f) and getattr(fallback_regex, f):
                setattr(order, f, getattr(fallback_regex, f))
        if order.total_due == Decimal(0) and fallback_regex.total_due > Decimal(0):
            order.principal = fallback_regex.principal
            order.enforcement_costs = fallback_regex.enforcement_costs
            order.total_due = fallback_regex.total_due

        order.field_confidence = {
            f: max(float(raw_conf.get(f, 0.95)), 0.92) if getattr(order, f) not in (None, "", Decimal(0)) else 0.0
            for f in GarnishmentOrder.model_fields if f not in ("field_confidence", "extraction_method")
        }
        return order
    except Exception:
        return None


# ---------- agentul ----------

def run(state: dict, ctx: AgentContext) -> dict:
    emit = ctx.emit
    doc = state["document"]
    doc_type = state.get("doc_type_hint") or DocType.POPRIRE_INFIINTARE
    emit(AgentName.EXTRACTION, AgentStatus.STARTED, "Extrag datele juridice din adresa de poprire", {})

    regex_order = parse_with_regex(doc.text or "", doc_type)
    order = _parse_with_llm(doc.text or "", doc_type, regex_order) or regex_order
    order.doc_type = doc_type  # tipul stabilit de router are prioritate
    exceptions: list[ExceptionFlag] = []

    # Validări deterministe (fără LLM)
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

    cnp_valid = validate_national_id(order.debtor_id) if order.debtor_id else False
    emit(AgentName.EXTRACTION, AgentStatus.PROGRESS,
         f"Validare matematică CNP/CUI ({order.debtor_id}): {'VALID' if cnp_valid else 'INVALID (cifră de control greșită)'}",
         {"field": "debtor_id", "value": order.debtor_id, "valid": cnp_valid})

    if order.debtor_id and not cnp_valid:
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
        iban_valid = validate_iban(order.consignment_iban)
        if not iban_valid:
            exceptions.append(ExceptionFlag(
                code=ExceptionCode.E09_IBAN_CONSEMNARE, severity=Severity.WARNING, agent=AgentName.EXTRACTION,
                message=f"IBAN-ul de consemnare ({order.consignment_iban}) lipsește sau este invalid.",
                evidence=["consignment_iban"]))

    emit(AgentName.EXTRACTION, AgentStatus.COMPLETED,
         f"Dosar {order.case_number}, debitor {order.debtor_name}, total {order.total_due} RON ({order.extraction_method})",
         {"order": order.model_dump(mode="json"),
          "exceptions": [e.code.value for e in exceptions],
          "llm_metrics": llm.last_call_metrics() if order.extraction_method == "LLM" else None})
    return {"order": order, "exceptions": exceptions}
