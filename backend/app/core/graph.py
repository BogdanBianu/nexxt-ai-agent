"""Motorul generic LangGraph cu cei 6 agenți post-router. Proprietar: Om1.

Toate modulele juridice (PopririZero, Sechestre, Cereri Autorități, Cereri GDPR)
rulează aceeași arhitectură de graf:

    extraction -> reconciliation -+-> (stop timpuriu / sistare) -> outcome
                                  +-> income_classifier -> rule_engine -> anomaly -> outcome

Dacă pachetul `langgraph` nu este disponibil în mediul de execuție, folosește automat
executorul secvențial determinist cu aceeași logică de rutare și aceleași evenimente SSE.
"""
from typing import Any, Callable

from app.contracts import AgentName, AgentStatus, DocType
from app.modules.popriri.state import PopririState, merge

NodeFn = Callable[[dict[str, Any], Any], dict[str, Any]]

REQUIRED_NODES = (
    "extraction",
    "reconciliation",
    "income_classifier",
    "rule_engine",
    "anomaly",
    "outcome",
)


def route_after_reconciliation(state: dict[str, Any]) -> str:
    """Decide după RECONCILIATION dacă graful continuă spre clasificarea veniturilor sau sare direct la OUTCOME."""
    if state.get("stop_after_reconciliation"):
        return "outcome"
    order = state.get("order")
    if order and order.doc_type == DocType.POPRIRE_SISTARE:
        return "outcome"
    return "income_classifier"


def emit_skipped_middle_agents(state: dict[str, Any], ctx: Any) -> None:
    """Când graful sare direct de la RECONCILIATION la OUTCOME, notifică UI-ul că nodurile intermediare au fost sărite."""
    order = state.get("order")
    reason = state.get("skip_reason") or (
        "Adresă de sistare poprire — nu necesită calcul de reținere"
        if order and order.doc_type == DocType.POPRIRE_SISTARE
        else "Excepție blocantă de reconciliere/identitate — oprire timpurie"
    )
    for agent_name in (AgentName.INCOME_CLASSIFIER, AgentName.RULE_ENGINE, AgentName.ANOMALY):
        ctx.emit(agent_name, AgentStatus.SKIPPED, reason, {"skipped": True})


def build_six_agent_langgraph(nodes: dict[str, NodeFn], ctx: Any):
    """Construiește și compilează un `StateGraph` LangGraph pentru un dicționar cu cei 6 agenți."""
    from langgraph.graph import END, START, StateGraph

    def outcome_with_skip_events(s: dict[str, Any]) -> dict[str, Any]:
        if route_after_reconciliation(s) == "outcome":
            emit_skipped_middle_agents(s, ctx)
        return nodes["outcome"](s, ctx)

    g = StateGraph(PopririState)
    for name in REQUIRED_NODES:
        fn = nodes[name]
        if name == "outcome":
            g.add_node(name, outcome_with_skip_events)
        else:
            g.add_node(name, lambda s, _fn=fn: _fn(s, ctx))

    g.add_edge(START, "extraction")
    g.add_edge("extraction", "reconciliation")
    g.add_conditional_edges(
        "reconciliation",
        route_after_reconciliation,
        {"outcome": "outcome", "income_classifier": "income_classifier"},
    )
    g.add_edge("income_classifier", "rule_engine")
    g.add_edge("rule_engine", "anomaly")
    g.add_edge("anomaly", "outcome")
    g.add_edge("outcome", END)
    return g.compile()


def run_six_agent_sequential(nodes: dict[str, NodeFn], state: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Executor secvențial echivalent cu graful LangGraph (fallback dacă `langgraph` nu e instalat)."""
    state = merge(dict(state), nodes["extraction"](state, ctx))
    state = merge(state, nodes["reconciliation"](state, ctx))
    if route_after_reconciliation(state) == "income_classifier":
        for name in ("income_classifier", "rule_engine", "anomaly"):
            state = merge(state, nodes[name](state, ctx))
    else:
        emit_skipped_middle_agents(state, ctx)
    return merge(state, nodes["outcome"](state, ctx))


def run_six_agent_graph(nodes: dict[str, NodeFn], initial: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Rulează cei 6 agenți prin LangGraph `StateGraph` (cu fallback la execuție secvențială)."""
    initial.setdefault("exceptions", [])
    try:
        graph = build_six_agent_langgraph(nodes, ctx)
    except ImportError:
        return run_six_agent_sequential(nodes, initial, ctx)
    return graph.invoke(initial)
