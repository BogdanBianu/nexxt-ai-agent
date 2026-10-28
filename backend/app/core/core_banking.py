"""Interfața către sistemul băncii + implementarea mock. Proprietar: Om2.

Agenții folosesc DOAR `CoreBankingPort`. În producție s-ar scrie un adaptor real;
în hackathon `CoreBankingMock` citește din `BankSnapshot`-ul scenariului.
"""
from datetime import date
from typing import Protocol

from app.contracts import (Account, ActiveGarnishment, BankSnapshot, Customer, HoldInstruction,
                           Transaction)


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
        return [a for a in self.snapshot.accounts if a.customer_id == customer_id]

    def get_transactions(self, customer_id: str, since: date | None = None) -> list[Transaction]:
        ibans = {a.iban for a in self.get_accounts(customer_id)}
        txs = [t for t in self.snapshot.transactions if t.iban in ibans]
        if since:
            txs = [t for t in txs if t.booking_date >= since]
        return sorted(txs, key=lambda t: t.booking_date)

    def get_active_garnishments(self, customer_id: str) -> list[ActiveGarnishment]:
        return [g for g in self.snapshot.active_garnishments if g.customer_id == customer_id and g.active]

    def place_hold(self, instruction: HoldInstruction) -> str:
        self.holds.append(instruction)
        return f"HOLD-{len(self.holds):04d}"
