from langchain_core.tools import tool
from src.agents.kg_pipeline import run_graph_search
from src.agents.rag_pipeline import run_vector_search


@tool
def vector_search(query: str) -> str:
    """Search the vector database for semantically similar content."""
    return run_vector_search(query)


@tool
def graph_search(query: str) -> str:
    """Search the knowledge graph for structured entity relationships."""
    return run_graph_search(query)
