from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from acnt_strat_synth.graph.state import GraphState
from acnt_strat_synth.graph.nodes import extract_node, score_node, synth_node


def _gate(state: GraphState):
    if state.get("review_required") and not state.get("approved"):
        return "wait"
    return "go"

def _wait_node(state: GraphState) -> GraphState:
    # Pause point: graph interrupts here
    return state

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("extract", extract_node)
    g.add_node("score", score_node)
    g.add_node("wait", _wait_node)
    g.add_node("synth", synth_node)

    g.add_edge(START, "extract")
    g.add_edge("extract", "score")
    g.add_conditional_edges("score", _gate, {"wait": "wait", "go": "synth"})
    g.add_edge("wait", "synth")
    g.add_edge("synth", END)

    return g.compile(checkpointer=MemorySaver(), interrupt_before=["wait"])