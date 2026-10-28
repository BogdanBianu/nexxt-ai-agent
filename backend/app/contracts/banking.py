"""Datele din sistemul băncii (Core Banking). În hackathon vin din mock (date sintetice)."""
from datetime import date, datetime

from pydantic import Field

from .common import Contract, Money
from .enums import AccountType, CreditorType, CustomerStatus, IncomeCategory, TxDirection


class Customer(Contract):
    customer_id: str
    full_name: str                              # "POPESCU ANDREI"
    national_id: str                            # CNP sau CUI
    is_legal_entity: bool = False
    status: CustomerStatus = CustomerStatus.ACTIV
    address: str | None = None


class Account(Contract):
    iban: str
    customer_id: str
    account_type: AccountType = AccountType.CURENT
    currency: str = "RON"
    opening_balance: Money = 0                  # sold la începutul ferestrei analizate
    current_balance: Money = 0


class Transaction(Contract):
    tx_id: str
    iban: str                                   # contul clientului
    booking_date: date
    direction: TxDirection
    amount: Money                               # mereu POZITIV; sensul e în `direction`
    counterparty_name: str
    counterparty_iban: str | None = None
    description: str = ""


class ActiveGarnishment(Contract):
    """O poprire deja înregistrată în bancă pe acest client."""
    garnishment_id: str
    customer_id: str
    case_number: str
    issuer_name: str
    creditor_name: str
    creditor_type: CreditorType
    total_due: Money
    amount_recovered: Money = 0
    monthly_periodic_take: Money = 0            # cât se reține lunar din salariu/pensie
    registered_at: datetime
    active: bool = True


class HoldInstruction(Contract):
    """Ordin de indisponibilizare trimis către Core Banking."""
    iban: str
    amount: Money
    reference: str                              # nr. dosar executare
    beneficiary_iban: str | None = None         # IBAN consemnare executor


class BankSnapshot(Contract):
    """Tot ce „știe” banca pentru un scenariu. Mock-ul Core Banking citește de aici."""
    customers: list[Customer] = Field(default_factory=list)
    accounts: list[Account] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    active_garnishments: list[ActiveGarnishment] = Field(default_factory=list)


class PayerRegistryEntry(Contract):
    """Plătitori cunoscuți (instituții publice, case de pensii) -> categorie implicită."""
    match: str                                  # subșir din numele plătitorului (fără diacritice, upper)
    iban: str | None = None
    default_category: IncomeCategory
    label: str
