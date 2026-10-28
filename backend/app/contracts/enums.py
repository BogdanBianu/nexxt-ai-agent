"""Enumerări comune pentru TOATĂ platforma LexOps.

REGULĂ DE ECHIPĂ: orice valoare nouă se adaugă AICI și în
frontend/src/types/contracts.ts, în același commit. Nu redenumiți valori existente.
"""
from enum import Enum


class DocType(str, Enum):
    """Tipul documentului juridic primit de bancă (stabilit de Intake Router + Extraction)."""
    POPRIRE_INFIINTARE = "POPRIRE_INFIINTARE"
    POPRIRE_SISTARE = "POPRIRE_SISTARE"
    POPRIRE_MODIFICARE = "POPRIRE_MODIFICARE"
    CERERE_INFORMATII = "CERERE_INFORMATII"      # executorul cere doar informații despre conturi
    CERERE_AUTORITATE = "CERERE_AUTORITATE"      # Poliție / Parchet / DNA -> modulul autoritati
    SECHESTRU_INSTITUIRE = "SECHESTRU_INSTITUIRE"    # sechestru asigurător fiscal / civil / penal -> modulul sechestre
    SECHESTRU_RIDICARE = "SECHESTRU_RIDICARE"        # ridicarea măsurii asigurătorii -> modulul sechestre
    NOTIFICARE_INSOLVENTA = "NOTIFICARE_INSOLVENTA"  # deschiderea procedurii (Legea 85/2014) -> modulul insolventa
    CERTIFICAT_MOSTENITOR = "CERTIFICAT_MOSTENITOR"  # certificat de moștenitor (notar) -> modulul insolventa
    CERERE_GDPR = "CERERE_GDPR"                  # Drepturi GDPR (Art. 15-22) / Solicitări ANSPDCP
    NECUNOSCUT = "NECUNOSCUT"


class IssuerType(str, Enum):
    EXECUTOR = "EXECUTOR"                        # Birou executor judecătoresc (BEJ)
    ANAF = "ANAF"
    ORGAN_FISCAL_LOCAL = "ORGAN_FISCAL_LOCAL"
    POLITIE = "POLITIE"
    PARCHET = "PARCHET"
    ANSPDCP = "ANSPDCP"                          # Autoritatea de Supraveghere Prelucrare Date
    PERSOANA_FIZICA = "PERSOANA_FIZICA"          # Solicitant persoană vizată
    ALTUL = "ALTUL"


class CreditorType(str, Enum):
    """Natura creanței. Determină cota din salariu (1/2 vs 1/3) și ordinea de preferință."""
    INTRETINERE = "INTRETINERE"                  # pensie alimentară, alocații
    FISCAL = "FISCAL"                            # ANAF, taxe locale
    COMERCIAL = "COMERCIAL"                      # bănci, IFN-uri, furnizori, altele


class IncomeCategory(str, Enum):
    """Natura juridică a unei încasări în cont."""
    SALARIU = "SALARIU"
    PENSIE = "PENSIE"
    ALOCATIE = "ALOCATIE"
    INDEMNIZATIE_COPIL = "INDEMNIZATIE_COPIL"
    DIURNA = "DIURNA"
    AJUTOR_SOCIAL = "AJUTOR_SOCIAL"
    INDEMNIZATIE_BOALA = "INDEMNIZATIE_BOALA"
    ALT_VENIT = "ALT_VENIT"
    SOLD_ANTERIOR = "SOLD_ANTERIOR"              # soldul existent înainte de fereastra analizată


class ClassificationMethod(str, Enum):
    HUMAN = "HUMAN"                              # override din Workbench (Om5)
    KEYWORD = "KEYWORD"
    PAYER_REGISTRY = "PAYER_REGISTRY"
    PATTERN = "PATTERN"
    LLM = "LLM"
    FALLBACK = "FALLBACK"                        # nu s-a putut clasifica sigur


class Severity(str, Enum):
    BLOCKING = "BLOCKING"                        # dosarul NU se procesează automat
    WARNING = "WARNING"                          # se procesează, dar ofițerul e avertizat


class ExceptionCode(str, Enum):
    E01_IDENTITATE = "E01"                       # CNP invalid / nume nu corespunde / client negăsit
    E02_DUPLICAT = "E02"                         # dosar de executare deja înregistrat
    E03_VENIT_AMBIGUU = "E03"                    # încasare cu natură neclară și impact mare
    E04_POPRIRI_CONCURENTE = "E04"               # plafon 1/2 atins, ordine de preferință
    E05_DOCUMENT_INVALID = "E05"                 # ilizibil / fără semnătură / câmp critic lipsă
    E06_SUSPICIUNE_ELUDARE = "E06"               # salariu reetichetat, golire cont etc.
    E07_SISTARE_FARA_POPRIRE = "E07"             # sistare pentru o poprire inexistentă
    E08_STATUT_CLIENT = "E08"                    # decedat / insolvență / cont special
    E09_IBAN_CONSEMNARE = "E09"                  # IBAN de consemnare invalid sau suspect


class CaseStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    AUTO_PROCESSED = "AUTO_PROCESSED"            # totul OK, ordin de blocare emis
    EXCEPTION_FLAGGED = "EXCEPTION_FLAGGED"      # așteaptă decizia ofițerului
    LIFTED = "LIFTED"                            # poprire ridicată (sistare)
    ROUTED_TO_OTHER_MODULE = "ROUTED_TO_OTHER_MODULE"
    FAILED = "FAILED"                            # eroare tehnică


class AgentName(str, Enum):
    INTAKE_ROUTER = "INTAKE_ROUTER"
    EXTRACTION = "EXTRACTION"
    RECONCILIATION = "RECONCILIATION"
    INCOME_CLASSIFIER = "INCOME_CLASSIFIER"
    RULE_ENGINE = "RULE_ENGINE"
    ANOMALY = "ANOMALY"
    OUTCOME = "OUTCOME"


class AgentStatus(str, Enum):
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ModuleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ROADMAP = "ROADMAP"


class CustomerStatus(str, Enum):
    ACTIV = "ACTIV"
    DECEDAT = "DECEDAT"
    INSOLVENTA = "INSOLVENTA"


class AccountType(str, Enum):
    CURENT = "CURENT"
    ECONOMII = "ECONOMII"
    DEPOZIT = "DEPOZIT"


class TxDirection(str, Enum):
    CREDIT = "CREDIT"                            # intrare în cont
    DEBIT = "DEBIT"                              # ieșire din cont
