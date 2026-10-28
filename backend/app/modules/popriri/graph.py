"""Graful de agenți al modulului de popriri (LangGraph). Proprietar: Om1.

    extraction -> reconciliation -+-> (stop: identitate / sistare) -> outcome
                                  +-> income_classifier -> rule_engine -> anomaly -> outcome

Dacă LangGraph nu e instalat, rulează un executor secvențial cu ACEEAȘI logică de rutare
(util pentru teste rapide și ca plasă de siguranță la demo).
"""
from app.contracts import DocType
from .agents import anomaly, extraction, income_classifier, outcome, reconciliation, rule_engine
from .agents.context import AgentContext
from .state import PopririState, merge

NODES = {
    "extraction": extraction.run,
    "reconciliation": reconciliation.run,
    "income_classifier": income_classifier.run,
    "rule_engine": rule_engine.run,
    "anomaly": anomaly.run,
    "outcome": outcome.run,
}


def route_after_reconciliation(state: dict) -> str:
    if state.get("stop_after_reconciliation"):
        return "outcome"
    if state["order"].doc_type == DocType.POPRIRE_SISTARE:
        return "outcome"
    return "income_classifier"


def build_langgraph(ctx: AgentContext):
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(PopririState)
    for name, fn in NODES.items():
        g.add_node(name, lambda s, _fn=fn: _fn(s, ctx))
    g.add_edge(START, "extraction")
    g.add_edge("extraction", "reconciliation")
    g.add_conditional_edges("reconciliation", route_after_reconciliation,
                            {"outcome": "outcome", "income_classifier": "income_classifier"})
    g.add_edge("income_classifier", "rule_engine")
    g.add_edge("rule_engine", "anomaly")
    g.add_edge("anomaly", "outcome")
    g.add_edge("outcome", END)
    return g.compile()


def run_sequential(state: dict, ctx: AgentContext) -> dict:
    state = merge(dict(state), NODES["extraction"](state, ctx))
    state = merge(state, NODES["reconciliation"](state, ctx))
    if route_after_reconciliation(state) == "income_classifier":
        for name in ("income_classifier", "rule_engine", "anomaly"):
            state = merge(state, NODES[name](state, ctx))
    return merge(state, NODES["outcome"](state, ctx))


def run_graph(initial: dict, ctx: AgentContext) -> dict:
    initial.setdefault("exceptions", [])
    try:
        graph = build_langgraph(ctx)
    except ImportError:
        return run_sequential(initial, ctx)
    return graph.invoke(initial)
