from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from src.agents.state import AgentState
from src.agents.agents import planner, vector_agent, kg_agent, direct_answer, answer_agent


def router(state: dict):
    route = state["route"]
    if route == "both":
        return [Send("vector", state), Send("kg", state)]
    return route


builder = StateGraph(AgentState)

builder.add_node("planner", planner)
builder.add_node("vector", vector_agent)
builder.add_node("kg", kg_agent)
builder.add_node("answer", answer_agent)
builder.add_node("direct", direct_answer)

builder.set_entry_point("planner")

builder.add_conditional_edges(
    "planner",
    router,
    {
        "vector": "vector",
        "kg": "kg",
        "direct": "direct",
    },
)

builder.add_edge("vector", "answer")
builder.add_edge("kg", "answer")
builder.add_edge("answer", END)
builder.add_edge("direct", END)

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)
