"""Agentul 4: Motorul de reguli (nod în graf). Proprietar: Om2.

Doar împachetează `engine.calculator.compute_decision` și emite evenimente. Fără LLM.
"""
from app.contracts import AgentName, AgentStatus
from app.modules.popriri.engine.calculator import compute_decision
from .context import AgentContext


def run(state: dict, ctx: AgentContext) -> dict:
    ctx.emit(AgentName.RULE_ENGINE, AgentStatus.STARTED, "Aplic regulile legale (calcul determinist)",
             {"rules_version": ctx.rulebook.version})
    decision, exc = compute_decision(state["order"], state.get("classified", []),
                                     state.get("active_garnishments", []), ctx.rulebook)
    for r in decision.rules_applied:
        ctx.emit(AgentName.RULE_ENGINE, AgentStatus.PROGRESS,
                 f"{r.rule_id}: din {r.base_amount} RON → urmăribil {r.seizable_amount} RON",
                 {"rule_id": r.rule_id, "legal_source": r.legal_source})
    ctx.emit(AgentName.RULE_ENGINE, AgentStatus.COMPLETED,
             f"De indisponibilizat: {decision.amount_to_hold} RON · protejat: {decision.amount_protected} RON",
             {"amount_to_hold": float(decision.amount_to_hold), "amount_protected": float(decision.amount_protected)})
    return {"decision": decision, "exceptions": exc}
