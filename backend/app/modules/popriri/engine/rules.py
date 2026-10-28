"""Încărcarea registrului de reguli (YAML). Proprietar: Om2."""
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from app import config
from app.contracts import CreditorType, IncomeCategory


@dataclass
class Rule:
    id: str
    legal_source: str
    description: str
    categories: list[IncomeCategory] = field(default_factory=list)
    creditor_types: list[CreditorType] = field(default_factory=list)
    quota: Decimal | None = None
    quota_if_creditor: dict[CreditorType, Decimal] = field(default_factory=dict)


@dataclass
class RuleBook:
    version: str
    salariu_minim_net: Decimal
    cumulative_cap: Decimal
    periodic_categories: set[IncomeCategory]
    rules: dict[str, Rule]
    creditor_priority: list[CreditorType] = field(default_factory=lambda: list(CreditorType))

    def rule(self, rule_id: str) -> Rule:
        return self.rules[rule_id]

    def rule_for(self, category: IncomeCategory, creditor: CreditorType) -> Rule | None:
        """Regula aplicabilă unei categorii de venit pentru un anumit tip de creditor."""
        for r in self.rules.values():
            if category in r.categories and (not r.creditor_types or creditor in r.creditor_types):
                return r
        return None

    def quota(self, rule: Rule, creditor: CreditorType) -> Decimal:
        return rule.quota_if_creditor.get(creditor, rule.quota or Decimal(0))

    def priority_rank(self, creditor: CreditorType) -> int:
        """0 = cel mai prioritar (R-PRIO-09). Tipurile nelistate vin la final."""
        try:
            return self.creditor_priority.index(creditor)
        except ValueError:
            return len(self.creditor_priority)

    def as_dict(self) -> dict:
        """Registrul serializabil pentru `GET /api/rules` (afișat în frontend)."""
        return {
            "version": self.version,
            "parameters": {
                "salariu_minim_net": float(self.salariu_minim_net),
                "cumulative_cap_on_periodic_income": float(self.cumulative_cap),
                "creditor_priority": [c.value for c in self.creditor_priority],
            },
            "periodic_categories": sorted(c.value for c in self.periodic_categories),
            "rules": [{
                "id": r.id,
                "legal_source": r.legal_source,
                "description": r.description,
                "categories": [c.value for c in r.categories],
                "creditor_types": [c.value for c in r.creditor_types],
                "quota": float(r.quota) if r.quota is not None else None,
                "quota_if_creditor": {k.value: float(v) for k, v in r.quota_if_creditor.items()},
            } for r in self.rules.values()],
        }


@lru_cache
def load_rulebook(path: str | None = None) -> RuleBook:
    raw = yaml.safe_load(Path(path or config.RULES_FILE).read_text(encoding="utf-8"))
    params = raw.get("parameters", {})
    rules = {}
    for r in raw["rules"]:
        rules[r["id"]] = Rule(
            id=r["id"], legal_source=r["legal_source"], description=r.get("description", ""),
            categories=[IncomeCategory(c) for c in r.get("categories", [])],
            creditor_types=[CreditorType(c) for c in r.get("creditor_types", [])],
            quota=Decimal(str(r["quota"])) if "quota" in r else None,
            quota_if_creditor={CreditorType(k): Decimal(str(v)) for k, v in r.get("quota_if_creditor", {}).items()},
        )
    return RuleBook(
        version=str(raw["version"]),
        salariu_minim_net=Decimal(str(params.get("salariu_minim_net", 0))),
        cumulative_cap=Decimal(str(params.get("cumulative_cap_on_periodic_income", "0.5"))),
        periodic_categories={IncomeCategory(c) for c in raw.get("periodic_categories", [])},
        rules=rules,
        creditor_priority=[CreditorType(c) for c in params.get("creditor_priority", [c.value for c in CreditorType])],
    )
