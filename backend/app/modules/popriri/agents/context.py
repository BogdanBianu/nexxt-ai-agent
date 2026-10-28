"""Contextul comun primit de fiecare agent (unelte + emitere evenimente)."""
from dataclasses import dataclass

from app.core.core_banking import CoreBankingPort
from app.core.events import EmitFn
from app.modules.popriri.engine.rules import RuleBook


@dataclass
class AgentContext:
    bank: CoreBankingPort
    emit: EmitFn
    rulebook: RuleBook
