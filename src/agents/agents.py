import os
from langchain_openai import ChatOpenAI
from src.agents.tools import vector_search, graph_search

llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))


def planner(state: dict) -> dict:
    question = state["question"]
    prompt = f"""You are a planner. Given the question below, decide which agent(s) should handle it.

Question: {question}

Return ONLY one word — no explanation, no punctuation:
vector   (use when the question requires semantic document search)
kg       (use when the question requires structured entity/relationship lookup)
both     (use when both vector and knowledge graph search are needed)
direct   (use when the question can be answered without retrieval)
"""
    route = llm.invoke(prompt).content.strip().lower()
    return {"route": route}


def vector_agent(state: dict) -> dict:
    result = vector_search.invoke(state["question"])
    return {"vector_result": result}


def kg_agent(state: dict) -> dict:
    result = graph_search.invoke(state["question"])
    return {"kg_result": result}


def direct_answer(state: dict) -> dict:
    answer = llm.invoke(state["question"]).content
    return {"answer": answer}


def answer_agent(state: dict) -> dict:
    prompt = f"""Answer the following question using the retrieved context below.

Question:
{state["question"]}

Vector Search Results:
{state.get("vector_result", "")}

Knowledge Graph Results:
{state.get("kg_result", "")}

Provide a clear, concise answer based on the context provided.
"""
    answer = llm.invoke(prompt).content
    return {"answer": answer}
