"""Documentele care intră în platformă și ce extragem din ele."""
from datetime import date, datetime

from pydantic import Field

from .common import Contract, Money
from .enums import CreditorType, DocType, IssuerType


class IncomingDocument(Contract):
    """Documentul brut, așa cum intră în bancă (upload, email, scenariu sintetic)."""
    document_id: str
    filename: str
    received_at: datetime
    content_type: str = "text/plain"            # "application/pdf" | "text/plain"
    text: str | None = None                     # textul (deja extras sau scenariu sintetic)
    pdf_path: str | None = None                 # cale relativă la data/ (dacă există PDF)


class GarnishmentOrder(Contract):
    """Datele structurate extrase dintr-o adresă de poprire (output Agent EXTRACTION)."""
    doc_type: DocType
    issuer_name: str                            # "BEJ Popescu Ion" / "AJFP Cluj"
    issuer_type: IssuerType
    case_number: str | None                     # nr. dosar de executare, ex. "1234/2026"
    issue_date: date | None
    debtor_name: str | None
    debtor_id: str | None                       # CNP (persoană fizică) sau CUI (firmă)
    creditor_name: str | None
    creditor_type: CreditorType = CreditorType.COMERCIAL
    principal: Money = 0
    enforcement_costs: Money = 0
    total_due: Money = 0
    consignment_iban: str | None = None         # contul în care banca virează sumele
    has_signature_and_stamp: bool = False
    references_case_number: str | None = None   # la sistare/modificare: dosarul vizat
    # încrederea pe câmp, 0..1 (cheie = numele câmpului de mai sus)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    extraction_method: str = "REGEX"            # "REGEX" | "LLM"
