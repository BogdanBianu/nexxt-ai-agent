"""Extractor și validator juridic dedicat pentru Măsuri Asigurătorii (Sechestre Asigurătorii).

Recunoaște documentele oficiale:
- Formular 504 ANAF DGAF / DGAMC — Decizie de instituire a măsurilor asigurătorii (Art. 213 CPF)
- Încheiere civilă executorie a instanței / Proces-verbal BEJ de sechestru asigurător (Art. 952-959 CPC)
- Ordonanță a procurorului de instituire a sechestrului asigurător penal (Art. 249-254 CPP / Legea 318/2015 ANABI)
- Decizie / Încheiere de ridicare a măsurii asigurătorii a sechestrului (Art. 956 CPC / Art. 213 alin. 13 CPF)
"""
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re

from app import config
from app.contracts import (
    AgentName, AgentStatus, CreditorType, DocType, ExceptionCode, ExceptionFlag,
    GarnishmentOrder, IssuerType, Severity, money,
)
from app.core.validators import normalize_text, validate_iban, validate_national_id
from app.modules.popriri.agents.context import AgentContext

SECHESTRE_REGISTRY_PATH = config.DATA_DIR / "sechestre_issuers_registry.json"
CRITICAL_FIELDS = ["case_number", "debtor_name", "debtor_id", "total_due"]


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


def load_sechestre_issuers() -> list[dict]:
    if not SECHESTRE_REGISTRY_PATH.exists():
        return []
    data = json.loads(SECHESTRE_REGISTRY_PATH.read_text(encoding="utf-8"))
    return data.get("issuers", [])


def parse_sechestru_order(text: str, doc_type: DocType) -> GarnishmentOrder:
    norm = normalize_text(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    first_line = lines[0] if lines else ""

    # 1. Identificare în registrul oficial al emitenților de sechestre (data/sechestre_issuers_registry.json)
    matched_issuer = None
    for entry in load_sechestre_issuers():
        if any(k in norm for k in entry.get("keywords", [])):
            matched_issuer = entry
            break

    if matched_issuer:
        issuer_name = matched_issuer["name"]
        issuer_type = IssuerType(matched_issuer["issuer_type"])
        default_creditor = CreditorType.FISCAL if issuer_type in (IssuerType.ANAF, IssuerType.PARCHET) else CreditorType.COMERCIAL
    elif "ANTIFRAUDA" in norm or "ADMINISTRARE FISCALA" in norm or "ANAF" in norm:
        issuer_name = first_line[:120]
        issuer_type, default_creditor = IssuerType.ANAF, CreditorType.FISCAL
    elif "PARCHETUL" in norm or "ANABI" in norm or "PROCUROR" in norm:
        issuer_name = first_line[:120]
        issuer_type, default_creditor = IssuerType.PARCHET, CreditorType.FISCAL
    elif "TRIBUNALUL" in norm or "CURTEA DE APEL" in norm or "EXECUTOR" in norm:
        issuer_name = first_line[:120]
        issuer_type, default_creditor = IssuerType.EXECUTOR, CreditorType.COMERCIAL
    else:
        issuer_name = first_line[:120]
        issuer_type, default_creditor = IssuerType.ALTUL, CreditorType.COMERCIAL

    nature = normalize_text(_find(r"(?:Natura crean[țt]ei|Temeiul m[ăa]surii|Regim juridic):\s*(.+)", text))
    if "FISCAL" in nature or "BUGETAR" in nature or "PENAL" in nature:
        creditor_type = CreditorType.FISCAL
    elif "INTRETINERE" in nature:
        creditor_type = CreditorType.INTRETINERE
    elif nature:
        creditor_type = CreditorType.COMERCIAL
    else:
        creditor_type = default_creditor

    debtor = re.search(
        r"(?:Debitor|Contribuabil|Debitor p[âa]r[âa]t|Inculpat|Persoana vizat[ăa])[^:\n]*:\s*([^,\n]+),\s*(?:CNP|C\.N\.P\.|CUI|CIF)[:\s]*([0-9]+)",
        text,
        re.I,
    )
    date_s = _find(r"Data(?:\s+emiterii)?:\s*(\d{2}\.\d{2}\.\d{4})", text)
    iban = _find(r"IBAN[:\s]*(RO[0-9A-Z ]{22,30})", text)
    iban = re.sub(r"\s", "", iban)[:24] if iban else (matched_issuer.get("consignment_iban") if matched_issuer else None)

    principal = _ro_amount(
        _find(r"(?:Debit principal|Obliga[țt]ii fiscale estimate|Crean[țt][ăa] garantat[ăa]|Prejudiciu estimat):\s*([\d\.\s]+,\d{2})", text)
    )
    costs = _ro_amount(
        _find(r"(?:Cheltuieli de executare|Cheltuieli judiciare|Accesorii estimate|Cau[țt]iune judiciar[ăa]):\s*([\d\.\s]+,\d{2})", text)
    )
    total = _ro_amount(
        _find(
            r"(?:Plafon m[ăa]sur[ăa] asigur[ăa]torie|Plafon sechestru asigur[ăa]tor|Total de indisponibilizat|Total de recuperat|Suma total[ăa]|p[âa]n[ăa] la concuren[țt]a sumei de):\s*([\d\.\s]+,\d{2})",
            text,
        )
    )

    case_no = _find(
        r"(?:Dosar(?:ul)? (?:de sechestru asigur[ăa]tor|administrativ-fiscal|de executare|penal|civil)|Decizia) (?:nr\.?)\s*([0-9]+(?:/[A-Z0-9]+)+)",
        text,
    )
    ref = _find(
        r"(?:instituit[ăa]|dispuse|înfiin[țt]at[ăa]|privind)[^\n]*?(?:dosar(?:ul)?|decizia)[^\n]*?nr\.?\s*([0-9]+(?:/[A-Z0-9]+)+)",
        text,
    )

    creditor_name = _find(
        r"(?:Creditor|Autoritate beneficiar[ăa]|Creditor reclamant|Parte civil[ăa])[^:\n]*:\s*(.+)",
        text,
    )

    order = GarnishmentOrder(
        doc_type=doc_type,
        issuer_name=issuer_name,
        issuer_type=issuer_type,
        case_number=case_no,
        issue_date=datetime.strptime(date_s, "%d.%m.%Y").date() if date_s else None,
        debtor_name=normalize_text(debtor.group(1)) if debtor else None,
        debtor_id=debtor.group(2) if debtor else None,
        creditor_name=creditor_name,
        creditor_type=creditor_type,
        principal=principal,
        enforcement_costs=costs,
        total_due=total,
        consignment_iban=iban,
        has_signature_and_stamp=bool(
            re.search(r"semn[ăa]tur[ăa] [șs]i [șs]tampil[ăa]|L\.S\.|semn[ăa]tur[ăa] electronic[ăa]", text, re.I)
        ),
        references_case_number=ref or (case_no if doc_type == DocType.POPRIRE_SISTARE else None),
        extraction_method="SECHESTRE_OFFICIAL_PARSER",
    )
    order.field_confidence = {
        f: (0.98 if getattr(order, f) not in (None, "", Decimal(0)) else 0.0)
        for f in GarnishmentOrder.model_fields
        if f not in ("field_confidence", "extraction_method")
    }
    return order


def run_sechestre_extraction(state: dict, ctx: AgentContext) -> dict:
    emit = ctx.emit
    doc = state["document"]
    doc_type = state.get("doc_type_hint") or DocType.POPRIRE_INFIINTARE
    emit(AgentName.EXTRACTION, AgentStatus.STARTED, "Extrag datele oficiale din actul de măsură asigurătorie (sechestru)", {})

    order = parse_sechestru_order(doc.text or "", doc_type)
    exceptions: list[ExceptionFlag] = []

    required_fields = [
        f for f in CRITICAL_FIELDS
        if not (f == "total_due" and doc_type == DocType.POPRIRE_SISTARE)
    ]
    missing = [
        f for f in required_fields
        if getattr(order, f) in (None, "", Decimal(0))
    ]
    low = [
        f for f in required_fields
        if f not in missing and order.field_confidence.get(f, 1.0) < config.MIN_FIELD_CONFIDENCE
    ]
    if missing or low:
        exceptions.append(
            ExceptionFlag(
                code=ExceptionCode.E05_DOCUMENT_INVALID,
                severity=Severity.BLOCKING,
                agent=AgentName.EXTRACTION,
                message="Câmpuri obligatorii lipsă din ordonanța/încheierea de sechestru: " + ", ".join(missing + low),
                evidence=missing + low,
            )
        )
    if not order.has_signature_and_stamp:
        exceptions.append(
            ExceptionFlag(
                code=ExceptionCode.E05_DOCUMENT_INVALID,
                severity=Severity.BLOCKING,
                agent=AgentName.EXTRACTION,
                message="Actul de instituire a sechestrului nu poartă semnătură și ștampilă / semnătură electronică calificată.",
                evidence=["has_signature_and_stamp"],
            )
        )

    cnp_valid = validate_national_id(order.debtor_id) if order.debtor_id else False
    emit(
        AgentName.EXTRACTION,
        AgentStatus.PROGRESS,
        f"Validare matematică CNP/CUI ({order.debtor_id}): {'VALID' if cnp_valid else 'INVALID'}",
        {"field": "debtor_id", "value": order.debtor_id, "valid": cnp_valid},
    )

    if order.debtor_id and not cnp_valid:
        exceptions.append(
            ExceptionFlag(
                code=ExceptionCode.E01_IDENTITATE,
                severity=Severity.BLOCKING,
                agent=AgentName.EXTRACTION,
                message=f"CNP/CUI-ul persoanei vizate de sechestru ({order.debtor_id}) este invalid matematic.",
                evidence=["debtor_id"],
            )
        )

    if doc_type != DocType.POPRIRE_SISTARE:
        if order.principal + order.enforcement_costs != order.total_due and order.principal > 0:
            exceptions.append(
                ExceptionFlag(
                    code=ExceptionCode.E05_DOCUMENT_INVALID,
                    severity=Severity.WARNING,
                    agent=AgentName.EXTRACTION,
                    message=f"Creanță garantată + accesorii ({order.principal} + {order.enforcement_costs}) ≠ plafon sechestru ({order.total_due}).",
                    evidence=["total_due"],
                )
            )
        if not validate_iban(order.consignment_iban):
            exceptions.append(
                ExceptionFlag(
                    code=ExceptionCode.E09_IBAN_CONSEMNARE,
                    severity=Severity.WARNING,
                    agent=AgentName.EXTRACTION,
                    message=f"IBAN-ul contului special de consemnare Trezorerie/ANABI ({order.consignment_iban}) este invalid.",
                    evidence=["consignment_iban"],
                )
            )

    emit(
        AgentName.EXTRACTION,
        AgentStatus.COMPLETED,
        f"Măsură asigurătorie extrasă: dosar {order.case_number}, debitor {order.debtor_name}, plafon {order.total_due} RON",
        {"order": order.model_dump(mode="json"), "exceptions": [e.code.value for e in exceptions]},
    )
    return {"order": order, "exceptions": exceptions}
