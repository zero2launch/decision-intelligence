## Multi Agent Workflow 

```bash
  
project/
│
├── app.py
├── tools.py
├── state.py
├── agents.py
└── graph.py

```

```
        User
        │
        ▼
        Planner
        │
        ├───────────────┐
        │               │
        ▼               ▼
        Vector Agent   KG Agent
        │               │
        ▼               ▼
        Vector Tool   Neo4j Tool
        │               │
        └───────┬───────┘
                ▼
        Answer Agent
                │
                ▼
        Save Memory + Checkpoint
                │
                ▼
            Final Answer

```

#### 1. state.py 

```python


from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]

    question: str

    route: str

    vector_result: str

    kg_result: str

    answer: str

```

#### 2. tools.py

```python
  
from langchain_core.tools import tool


@tool
def vector_search(query: str):
    """
    Search Vector Database
    """

    # Replace with Chromadb/Pinecone/FAISS/Azure AI Search

    return f"Vector Result for: {query}"


@tool
def graph_search(query: str):
    """
    Search Knowledge Graph
    """

    # Replace with Neo4j

    return f"Knowledge Graph Result for: {query}"

```

#### 3. agents.py 

```python

from langchain_openai import ChatOpenAI

from langchain_core.messages import HumanMessage

from tools import vector_search, graph_search

llm = ChatOpenAI(model="gpt-5.4-mini")

```

#### Planner Agent 

```python

def planner(state):

    question = state["question"]

    prompt = f"""
You are a planner.

Question:
{question}

Return ONLY one word:

vector
kg
both
direct
"""

    route = llm.invoke(prompt).content.strip().lower()

    return {
        "route": route
    }

```

#### Vector Agent

```python
  
  def vector_agent(state):

    docs = vector_search.invoke(state["question"])

    return {
        "vector_result": docs
    }

```

#### KG Agent

```python

  def kg_agent(state):

    graph = graph_search.invoke(state["question"])

    return {
        "kg_result": graph
    }

```

#### Direct Answer 

```python

   def direct_answer(state):

    answer = llm.invoke(state["question"]).content

    return {
        "answer": answer
    }

```

#### Answer Agent 


```python
   
   def answer_agent(state):

    prompt = f"""
Question

{state['question']}


Vector Search

{state.get('vector_result','')}


Knowledge Graph

{state.get('kg_result','')}

Answer the question.
"""

    answer = llm.invoke(prompt).content

    return {
        "answer": answer
    }

```

#### 4. graph.py 

```python

from langgraph.graph import StateGraph

from state import AgentState

from agents import *

builder = StateGraph(AgentState)

builder.add_node("planner", planner)

builder.add_node("vector", vector_agent)

builder.add_node("kg", kg_agent)

builder.add_node("answer", answer_agent)

builder.add_node("direct", direct_answer)

```
#### Conditional routing

```python 
   
    def router(state):

      return state["route"]

    builder.set_entry_point("planner")

    builder.add_conditional_edges(
        "planner",
        router,
        {
            "vector": "vector",
            "kg": "kg",
            "both": ["vector", "kg"],
            "direct": "direct"
        }
    ) 

    builder.add_edge("vector", "answer")

    builder.add_edge("kg", "answer")

    builder.set_finish_point("answer")

    builder.set_finish_point("direct")

```

#### 5. checkpointer.py 

```python

from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()

graph = builder.compile(
    checkpointer=memory
)

```

#### 6. app.py

```python

from graph import graph

config = {
    "configurable": {
        "thread_id": "user_101"
    }
}

response = graph.invoke(
    {
        "question": "Who bought Samsung products and what is their warranty?"
    },
    config=config
)

print(response["answer"])

```