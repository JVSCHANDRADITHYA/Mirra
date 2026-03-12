"""
graph.py — The LangGraph state machine.
─────────────────────────────────────────
Wires all agents together with:
  - Deterministic routing (no LLM supervisor needed)
  - HIL checkpoints via interrupt()
  - Verification → assembly retry loop
  - MemorySaver checkpointer for resumable runs
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state import SiteBuilderState
from agents.scrape_agent import scrape_agent
from agents.styling_agent import styling_agent
from agents.structure_agent import structure_agent
from agents.content_agent import content_agent
from agents.assembly_agent import assembly_agent
from agents.verification_agent import verification_agent


# ─── Deterministic router ─────────────────────────────────────────────────────

def route(state: SiteBuilderState) -> str:
    """
    Pure code routing — no LLM involved.
    Reads current_step from state and returns the next node name.
    """
    step = state.get("current_step", "scrape")

    routing_map = {
        "scrape":                   "scrape_agent",
        "styling":                  "styling_agent",
        "structure":                "structure_agent",
        "hil_structure_approval":   "content_agent",   # HIL happens inside content_agent
        "assembly":                 "assembly_agent",
        "verification":             "verification_agent",
        "done":                     END,
    }

    return routing_map.get(step, END)


# ─── Build the graph ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(SiteBuilderState)

    # Add all agent nodes
    builder.add_node("scrape_agent",        scrape_agent)
    builder.add_node("styling_agent",       styling_agent)
    builder.add_node("structure_agent",     structure_agent)
    builder.add_node("content_agent",       content_agent)
    builder.add_node("assembly_agent",      assembly_agent)
    builder.add_node("verification_agent",  verification_agent)

    # Entry point
    builder.set_entry_point("scrape_agent")

    # Linear edges with deterministic routing
    builder.add_edge("scrape_agent",    "styling_agent")
    builder.add_edge("styling_agent",   "structure_agent")
    builder.add_edge("structure_agent", "content_agent")
    builder.add_edge("content_agent",   "assembly_agent")

    # Verification has a conditional loop-back to assembly
    builder.add_conditional_edges(
        "assembly_agent",
        lambda s: "verification_agent",   # always verify after assembly
    )

    builder.add_conditional_edges(
        "verification_agent",
        _verification_router,
    )

    return builder


def _verification_router(state: SiteBuilderState) -> str:
    """Route after verification: retry assembly or finish."""
    if state.get("verified"):
        return END
    if state.get("retry_count", 0) >= 2:
        return END   # give up after 2 retries
    return "assembly_agent"


# ─── Compiled app (with HIL checkpointing) ────────────────────────────────────

def create_app():
    """
    Returns compiled LangGraph app with MemorySaver for HIL support.
    
    MemorySaver stores state in memory.
    For production, swap with SqliteSaver or RedisSaver.
    """
    checkpointer = MemorySaver()
    graph = build_graph()

    app = graph.compile(
        checkpointer=checkpointer,
        # NO interrupt_before — interrupt() inside content_agent handles HIL
    )

    return app