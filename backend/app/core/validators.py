"""Validatoare deterministe (fără LLM). Proprietar: Om2.

Rapide, testate unitar, și foarte convingătoare la demo:
„CNP-ul din adresă are cifra de control greșită” se vede în 1 ms.
"""
import re
import unicodedata

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
