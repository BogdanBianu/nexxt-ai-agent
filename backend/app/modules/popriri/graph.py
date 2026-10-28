"""Graful de agenți al modulului de popriri (LangGraph). Proprietar: Om1.

    extraction -> reconciliation -+-> (stop: identitate / sistare) -> outcome
                                  +-> income_classifier -> rule_engine -> anomaly -> outcome

Folosește motorul comun LangGraph din `app.core.graph`.
"""
from app.core.graph import (
    build_six_agent_langgraph,
    emit_skipped_middle_agents as _emit_skipped_middle_agents,
    route_after_reconciliation,
    run_six_agent_graph,
    run_six_agent_sequential,
)
from .agents import anomaly, extraction, income_classifier, outcome, reconciliation, rule_engine
from .agents.context import AgentContext

NODES = {
    "extraction": extraction.run,
    "reconciliation": reconciliation.run,
    "income_classifier": income_classifier.run,
    "rule_engine": rule_engine.run,
    "anomaly": anomaly.run,
    "outcome": outcome.run,
}


def build_langgraph(ctx: AgentContext):
    return build_six_agent_langgraph(NODES, ctx)


def run_sequential(state: dict, ctx: AgentContext) -> dict:
    return run_six_agent_sequential(NODES, state, ctx)


def run_graph(initial: dict, ctx: AgentContext) -> dict:
    return run_six_agent_graph(NODES, initial, ctx)
