"""Validatoare deterministe (fără LLM). Proprietar: Om2.

Rapide, testate unitar, și foarte convingătoare la demo:
„CNP-ul din adresă are cifra de control greșită” se vede în 1 ms.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_CNP_WEIGHTS = "279146358279"
_CUI_WEIGHTS = "753217532"


def normalize_text(value: str | None) -> str:
    """Fără diacritice, majuscule, spații simple. Folosit la potriviri de nume și cuvinte cheie."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip().upper()


def cnp_control_digit(first12: str) -> int:
    total = sum(int(d) * int(w) for d, w in zip(first12, _CNP_WEIGHTS))
    rest = total % 11
    return 1 if rest == 10 else rest


def validate_cnp(cnp: str | None) -> bool:
    if not cnp or not re.fullmatch(r"[1-9]\d{12}", cnp):
        return False
    month, day = int(cnp[3:5]), int(cnp[5:7])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return cnp_control_digit(cnp[:12]) == int(cnp[12])


def cui_control_digit(body: str) -> int:
    padded = body.rjust(9, "0")
    total = sum(int(d) * int(w) for d, w in zip(padded, _CUI_WEIGHTS))
    rest = (total * 10) % 11
    return 0 if rest == 10 else rest


def validate_cui(cui: str | None) -> bool:
    if not cui:
        return False
    cui = cui.upper().removeprefix("RO").strip()
    if not re.fullmatch(r"\d{2,10}", cui):
        return False
    return cui_control_digit(cui[:-1]) == int(cui[-1])


def validate_iban(iban: str | None) -> bool:
    if not iban:
        return False
    iban = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    if iban.startswith("RO") and len(iban) != 24:
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


# Codurile de bancă (primele 4 caractere ale BIC-ului) care apar în IBAN-urile RO, poziția 5-8.
RO_BANK_CODES: dict[str, str] = {
    "TREZ": "Trezoreria Statului",
    "NBOR": "Banca Națională a României",
    "RZBR": "Raiffeisen Bank",
    "BTRL": "Banca Transilvania",
    "BRDE": "BRD - Groupe Société Générale",
    "RNCB": "Banca Comercială Română",
    "INGB": "ING Bank",
    "BACX": "UniCredit Bank",
    "CECE": "CEC Bank",
    "OTPV": "OTP Bank",
    "BUCU": "Alpha Bank",
    "UGBI": "Garanti BBVA",
    "BITR": "Intesa Sanpaolo Bank",
    "PIRB": "First Bank",
    "FNNB": "Credit Europe Bank",
    "CARP": "Patria Bank",
    "EXIM": "EximBank",
    "BREL": "Libra Internet Bank",
    "PORL": "ProCredit Bank",
    # IBAN-ul exemplu din standard, folosit în scenariile sintetice
    "AAAA": "Bancă de test (IBAN exemplu)",
}
TREASURY_CODE = "TREZ"


def iban_bank_code(iban: str | None) -> str | None:
    """Codul băncii dintr-un IBAN românesc (ex. RO49 RZBR ... -> "RZBR"); None dacă nu e IBAN RO."""
    if not iban:
        return None
    iban = iban.replace(" ", "").upper()
    if not iban.startswith("RO") or len(iban) < 8:
        return None
    return iban[4:8]


@dataclass(frozen=True)
class IbanCheck:
    ok: bool
    bank_code: str | None
    bank_name: str | None
    is_treasury: bool
    reason: str                                 # mesaj în română, afișabil ofițerului


def check_consignment_iban(iban: str | None, expect_treasury: bool = False) -> IbanCheck:
    """IBAN-ul de consemnare: valid mod-97, românesc, emis de o bancă/trezorerie cunoscută.

    `expect_treasury=True` pentru creanțe fiscale (ANAF / organe fiscale locale), unde sumele
    se virează într-un cont de Trezorerie.
    """
    if not validate_iban(iban):
        return IbanCheck(False, None, None, False, f"IBAN-ul de consemnare ({iban}) lipsește sau este invalid.")
    code = iban_bank_code(iban)
    if code is None:
        return IbanCheck(False, None, None, False, f"IBAN-ul de consemnare ({iban}) nu este un cont din România.")
    name = RO_BANK_CODES.get(code)
    if name is None:
        return IbanCheck(False, code, None, False,
                         f"Codul de bancă {code} din IBAN-ul de consemnare nu aparține unei bănci din România.")
    is_treasury = code == TREASURY_CODE
    if expect_treasury and not is_treasury:
        return IbanCheck(False, code, name, False,
                         f"Creanță fiscală, dar IBAN-ul de consemnare este la {name}, nu la Trezoreria Statului.")
    return IbanCheck(True, code, name, is_treasury, f"Cont de consemnare la {name}.")


def validate_issue_date(issue_date: date | None, received: date | None = None) -> bool:
    """Data emiterii adresei există și nu e în viitor față de data primirii (implicit: azi)."""
    return issue_date is not None and issue_date <= (received or date.today())


def validate_amounts(principal: Decimal, costs: Decimal, total: Decimal) -> bool:
    """Debit principal + cheltuieli de executare = total de recuperat."""
    return principal + costs == total


def validate_national_id(value: str | None) -> bool:
    """CNP (13 cifre) sau CUI (2-10 cifre)."""
    if not value:
        return False
    value = value.strip()
    return validate_cnp(value) if len(value) == 13 else validate_cui(value)


def names_match(a: str | None, b: str | None) -> bool:
    """Potrivire tolerantă: aceleași cuvinte, în orice ordine, fără diacritice."""
    ta, tb = set(normalize_text(a).replace("-", " ").split()), set(normalize_text(b).replace("-", " ").split())
    return bool(ta) and ta == tb
