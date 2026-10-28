"""Interfața către sistemul băncii + implementarea mock. Proprietar: Om2.

Agenții folosesc DOAR `CoreBankingPort`. În producție s-ar scrie un adaptor real;
în hackathon `CoreBankingMock` citește din `BankSnapshot`-ul scenariului.
"""
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.contracts import (Account, ActiveGarnishment, BankSnapshot, Customer, HoldInstruction,
                           Transaction, money)

# Cursuri BNR mock (RON pentru 1 unitate). În producție: cursul BNR din ziua indisponibilizării.
BNR_RATES_MOCK: dict[str, Decimal] = {
    "RON": Decimal("1"),
    "EUR": Decimal("4.9750"),
    "USD": Decimal("4.5820"),
    "GBP": Decimal("5.8930"),
    "CHF": Decimal("5.3010"),
}


def fx_rate(currency: str) -> Decimal:
    try:
        return BNR_RATES_MOCK[currency.upper()]
    except KeyError:
        raise ValueError(f"Nu există curs BNR pentru moneda {currency}") from None


def to_ron(amount: Decimal, currency: str) -> Decimal:
    return money(Decimal(amount) * fx_rate(currency))


class CoreBankingPort(Protocol):
    def find_customer(self, national_id: str) -> Customer | None: ...
    def get_accounts(self, customer_id: str) -> list[Account]: ...
    def get_transactions(self, customer_id: str, since: date | None = None) -> list[Transaction]: ...
    def get_active_garnishments(self, customer_id: str) -> list[ActiveGarnishment]: ...
    def place_hold(self, instruction: HoldInstruction) -> str: ...


class CoreBankingMock:
    def __init__(self, snapshot: BankSnapshot):
        self.snapshot = snapshot
        self.holds: list[HoldInstruction] = []

    def find_customer(self, national_id: str) -> Customer | None:
        return next((c for c in self.snapshot.customers if c.national_id == national_id), None)

    def get_accounts(self, customer_id: str) -> list[Account]:
        """Conturile clientului, cu soldurile din valută convertite în RON (ca și tranzacțiile).

        Agenții adună solduri direct (ex. SOLD_ANTERIOR); un sold de 1.000 EUR nu are voie
        să intre în calcul ca 1.000 RON.
        """
        return [self._account_in_ron(a) for a in self._raw_accounts(customer_id)]

    def _raw_accounts(self, customer_id: str) -> list[Account]:
        return [a for a in self.snapshot.accounts if a.customer_id == customer_id]

    @staticmethod
    def _account_in_ron(acc: Account) -> Account:
        if acc.currency.upper() == "RON":
            return acc
        return acc.model_copy(update={"opening_balance": to_ron(acc.opening_balance, acc.currency),
                                      "current_balance": to_ron(acc.current_balance, acc.currency),
                                      "currency": "RON"})

    def get_transactions(self, customer_id: str, since: date | None = None) -> list[Transaction]:
        """Tranzacțiile tuturor conturilor clientului, cu sumele din conturile în valută convertite în RON.

        Poprirea se calculează în RON, deci agenții primesc direct echivalentul; suma originală
        rămâne vizibilă în descriere (ex. „[1.000,00 EUR × 4,9750]”).
        """
        currency = {a.iban: a.currency for a in self._raw_accounts(customer_id)}
        txs = [self._in_ron(t, currency[t.iban]) for t in self.snapshot.transactions if t.iban in currency]
        if since:
            txs = [t for t in txs if t.booking_date >= since]
        return sorted(txs, key=lambda t: t.booking_date)

    @staticmethod
    def _in_ron(tx: Transaction, currency: str) -> Transaction:
        if currency.upper() == "RON":
            return tx
        rate = fx_rate(currency)
        note = f"[{tx.amount} {currency.upper()} × {rate} curs BNR]"
        return tx.model_copy(update={"amount": to_ron(tx.amount, currency),
                                     "description": f"{tx.description} {note}".strip()})

    def balance_in_ron(self, customer_id: str) -> Decimal:
        """Soldul curent cumulat al tuturor conturilor clientului, în RON."""
        return money(sum((a.current_balance for a in self.get_accounts(customer_id)), Decimal(0)))

    def get_active_garnishments(self, customer_id: str) -> list[ActiveGarnishment]:
        return [g for g in self.snapshot.active_garnishments if g.customer_id == customer_id and g.active]

    def place_hold(self, instruction: HoldInstruction) -> str:
        self.holds.append(instruction)
        return f"HOLD-{len(self.holds):04d}"
