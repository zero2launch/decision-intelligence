import os
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
from typing import get_type_hints
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_state():
    return {
        "messages": [],
        "question": "Who bought Samsung products?",
        "route": "",
        "vector_result": "",
        "kg_result": "",
        "answer": "",
    }


# ---------------------------------------------------------------------------
# S — AgentState structure
# ---------------------------------------------------------------------------

class TestAgentState:
    def test_S01_has_all_required_fields(self):
        from src.agents.state import AgentState
        annotations = AgentState.__annotations__
        for field in ("messages", "question", "route", "vector_result", "kg_result", "answer"):
            assert field in annotations

    def test_S02_messages_uses_add_messages_reducer(self):
        from src.agents.state import AgentState
        from langgraph.graph.message import add_messages
        hints = get_type_hints(AgentState, include_extras=True)
        metadata = hints["messages"].__metadata__
        assert add_messages in metadata

    def test_S03_state_can_be_constructed_with_all_fields(self):
        from src.agents.state import AgentState
        state: AgentState = {
            "messages": [],
            "question": "test",
            "route": "vector",
            "vector_result": "result",
            "kg_result": "kg",
            "answer": "answer",
        }
        assert state["question"] == "test"


# ---------------------------------------------------------------------------
# T — Placeholder tools
# ---------------------------------------------------------------------------

class TestTools:
    def test_T01_vector_search_is_langchain_tool(self):
        from src.agents.tools import vector_search
        assert hasattr(vector_search, "invoke")
        assert vector_search.name == "vector_search"

    def test_T02_vector_search_returns_string(self):
        from src.agents.tools import vector_search
        result = vector_search.invoke("Samsung")
        assert isinstance(result, str) and result

    def test_T03_vector_search_result_reflects_query(self):
        from src.agents.tools import vector_search
        result = vector_search.invoke("Samsung")
        assert "Samsung" in result

    def test_T04_graph_search_is_langchain_tool(self):
        from src.agents.tools import graph_search
        assert hasattr(graph_search, "invoke")
        assert graph_search.name == "graph_search"

    def test_T05_graph_search_returns_string(self):
        with patch("src.agents.tools.run_graph_search", return_value="Graph result"):
            from src.agents.tools import graph_search
            result = graph_search.invoke("Samsung")
        assert isinstance(result, str) and result

    def test_T06_graph_search_result_reflects_query(self):
        with patch("src.agents.tools.run_graph_search", return_value="Graph result about Samsung"):
            from src.agents.tools import graph_search
            result = graph_search.invoke("Samsung")
        assert "Samsung" in result

    def test_T07_vector_search_has_description(self):
        from src.agents.tools import vector_search
        assert len(vector_search.description) > 0

    def test_T08_graph_search_has_description(self):
        from src.agents.tools import graph_search
        assert len(graph_search.description) > 0


# ---------------------------------------------------------------------------
# P — Planner agent
# ---------------------------------------------------------------------------

class TestPlannerAgent:
    def _mock_llm(self, content: str):
        mock = MagicMock()
        mock.invoke.return_value.content = content
        return mock

    def test_P01_routes_to_vector(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("vector")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert result == {"route": "vector"}

    def test_P02_routes_to_kg(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("kg")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert result == {"route": "kg"}

    def test_P03_routes_to_both(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("both")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert result == {"route": "both"}

    def test_P04_routes_to_direct(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("direct")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert result == {"route": "direct"}

    def test_P05_strips_whitespace(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("  vector  ")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert result == {"route": "vector"}

    def test_P06_lowercases_response(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("VECTOR")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert result == {"route": "vector"}

    def test_P07_only_sets_route_key(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("vector")):
            from src.agents.agents import planner
            result = planner(base_state)
            assert set(result.keys()) == {"route"}

    def test_P08_passes_question_to_llm(self, base_state):
        base_state["question"] = "What is 2+2?"
        mock = self._mock_llm("direct")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import planner
            planner(base_state)
            assert mock.invoke.call_count == 1
            call_arg = mock.invoke.call_args[0][0]
            assert "What is 2+2?" in call_arg


# ---------------------------------------------------------------------------
# VA — Vector agent
# ---------------------------------------------------------------------------

class TestVectorAgent:
    def test_VA01_returns_vector_result_key(self, base_state):
        with patch("src.agents.agents.vector_search") as mock_tool:
            mock_tool.invoke.return_value = "some result"
            from src.agents.agents import vector_agent
            result = vector_agent(base_state)
            assert result == {"vector_result": "some result"}

    def test_VA02_only_sets_vector_result(self, base_state):
        with patch("src.agents.agents.vector_search") as mock_tool:
            mock_tool.invoke.return_value = "some result"
            from src.agents.agents import vector_agent
            result = vector_agent(base_state)
            assert set(result.keys()) == {"vector_result"}

    def test_VA03_calls_invoke_with_question(self, base_state):
        base_state["question"] = "Samsung warranty"
        with patch("src.agents.agents.vector_search") as mock_tool:
            mock_tool.invoke.return_value = "result"
            from src.agents.agents import vector_agent
            vector_agent(base_state)
            mock_tool.invoke.assert_called_once_with("Samsung warranty")

    def test_VA04_result_is_string(self, base_state):
        with patch("src.agents.agents.vector_search") as mock_tool:
            mock_tool.invoke.return_value = "some result"
            from src.agents.agents import vector_agent
            result = vector_agent(base_state)
            assert isinstance(result["vector_result"], str)


# ---------------------------------------------------------------------------
# KG — KG agent
# ---------------------------------------------------------------------------

class TestKgAgent:
    def test_KG01_returns_kg_result_key(self, base_state):
        with patch("src.agents.agents.graph_search") as mock_tool:
            mock_tool.invoke.return_value = "some kg result"
            from src.agents.agents import kg_agent
            result = kg_agent(base_state)
            assert result == {"kg_result": "some kg result"}

    def test_KG02_only_sets_kg_result(self, base_state):
        with patch("src.agents.agents.graph_search") as mock_tool:
            mock_tool.invoke.return_value = "some kg result"
            from src.agents.agents import kg_agent
            result = kg_agent(base_state)
            assert set(result.keys()) == {"kg_result"}

    def test_KG03_calls_invoke_with_question(self, base_state):
        base_state["question"] = "Samsung warranty"
        with patch("src.agents.agents.graph_search") as mock_tool:
            mock_tool.invoke.return_value = "result"
            from src.agents.agents import kg_agent
            kg_agent(base_state)
            mock_tool.invoke.assert_called_once_with("Samsung warranty")

    def test_KG04_result_is_string(self, base_state):
        with patch("src.agents.agents.graph_search") as mock_tool:
            mock_tool.invoke.return_value = "some kg result"
            from src.agents.agents import kg_agent
            result = kg_agent(base_state)
            assert isinstance(result["kg_result"], str)


# ---------------------------------------------------------------------------
# DA — Direct answer agent
# ---------------------------------------------------------------------------

class TestDirectAnswer:
    def _mock_llm(self, content: str):
        mock = MagicMock()
        mock.invoke.return_value.content = content
        return mock

    def test_DA01_returns_answer_key(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("The answer is 42.")):
            from src.agents.agents import direct_answer
            result = direct_answer(base_state)
            assert result == {"answer": "The answer is 42."}

    def test_DA02_only_sets_answer(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("42")):
            from src.agents.agents import direct_answer
            result = direct_answer(base_state)
            assert set(result.keys()) == {"answer"}

    def test_DA03_passes_question_to_llm(self, base_state):
        base_state["question"] = "What is 2+2?"
        mock = self._mock_llm("4")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import direct_answer
            direct_answer(base_state)
            mock.invoke.assert_called_once_with("What is 2+2?")

    def test_DA04_does_not_call_tools(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("answer")), \
             patch("src.agents.agents.vector_search") as mock_vs, \
             patch("src.agents.agents.graph_search") as mock_gs:
            from src.agents.agents import direct_answer
            direct_answer(base_state)
            mock_vs.invoke.assert_not_called()
            mock_gs.invoke.assert_not_called()


# ---------------------------------------------------------------------------
# AA — Answer synthesis agent
# ---------------------------------------------------------------------------

class TestAnswerAgent:
    def _mock_llm(self, content: str):
        mock = MagicMock()
        mock.invoke.return_value.content = content
        return mock

    def test_AA01_returns_answer_key(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("Synthesized answer.")):
            from src.agents.agents import answer_agent
            result = answer_agent(base_state)
            assert result == {"answer": "Synthesized answer."}

    def test_AA02_only_sets_answer(self, base_state):
        with patch("src.agents.agents.llm", self._mock_llm("answer")):
            from src.agents.agents import answer_agent
            result = answer_agent(base_state)
            assert set(result.keys()) == {"answer"}

    def test_AA03_prompt_includes_question(self, base_state):
        base_state["question"] = "Samsung warranty"
        mock = self._mock_llm("answer")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import answer_agent
            answer_agent(base_state)
            call_arg = mock.invoke.call_args[0][0]
            assert "Samsung warranty" in call_arg

    def test_AA04_prompt_includes_vector_result(self, base_state):
        base_state["vector_result"] = "some docs"
        mock = self._mock_llm("answer")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import answer_agent
            answer_agent(base_state)
            call_arg = mock.invoke.call_args[0][0]
            assert "some docs" in call_arg

    def test_AA05_prompt_includes_kg_result(self, base_state):
        base_state["kg_result"] = "entity data"
        mock = self._mock_llm("answer")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import answer_agent
            answer_agent(base_state)
            call_arg = mock.invoke.call_args[0][0]
            assert "entity data" in call_arg

    def test_AA06_missing_vector_result_no_error(self, base_state):
        base_state.pop("vector_result", None)
        mock = self._mock_llm("answer")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import answer_agent
            answer_agent(base_state)
            assert mock.invoke.call_count == 1

    def test_AA07_missing_kg_result_no_error(self, base_state):
        base_state.pop("kg_result", None)
        mock = self._mock_llm("answer")
        with patch("src.agents.agents.llm", mock):
            from src.agents.agents import answer_agent
            answer_agent(base_state)
            assert mock.invoke.call_count == 1


# ---------------------------------------------------------------------------
# R — Router function
# ---------------------------------------------------------------------------

class TestRouterFunction:
    def test_R01_routes_to_vector(self):
        from src.agents.graph import router
        assert router({"route": "vector"}) == "vector"

    def test_R02_routes_to_kg(self):
        from src.agents.graph import router
        assert router({"route": "kg"}) == "kg"

    def test_R03_routes_to_direct(self):
        from src.agents.graph import router
        assert router({"route": "direct"}) == "direct"

    def test_R04_both_returns_list_of_two_sends(self):
        from src.agents.graph import router
        result = router({"route": "both"})
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(s, Send) for s in result)

    def test_R05_both_sends_target_vector_and_kg(self):
        from src.agents.graph import router
        result = router({"route": "both"})
        nodes = {s.node for s in result}
        assert nodes == {"vector", "kg"}


# ---------------------------------------------------------------------------
# GC — Graph compilation
# ---------------------------------------------------------------------------

class TestGraphCompilation:
    def test_GC01_graph_compiles_without_error(self):
        from src.agents.graph import graph
        assert graph is not None

    def test_GC02_memory_saver_is_used(self):
        from src.agents.graph import memory
        assert isinstance(memory, MemorySaver)

    def test_GC03_graph_has_planner_node(self):
        from src.agents.graph import graph
        assert "planner" in graph.nodes

    def test_GC04_graph_has_vector_node(self):
        from src.agents.graph import graph
        assert "vector" in graph.nodes

    def test_GC05_graph_has_kg_node(self):
        from src.agents.graph import graph
        assert "kg" in graph.nodes

    def test_GC06_graph_has_answer_node(self):
        from src.agents.graph import graph
        assert "answer" in graph.nodes

    def test_GC07_graph_has_direct_node(self):
        from src.agents.graph import graph
        assert "direct" in graph.nodes


# ---------------------------------------------------------------------------
# CP — Checkpointing / thread isolation
# ---------------------------------------------------------------------------

class TestCheckpointing:
    def _llm_mock(self, *contents):
        mock = MagicMock()
        mock.invoke.side_effect = [MagicMock(content=c) for c in contents]
        return mock

    def test_CP01_graph_accepts_config_with_thread_id(self):
        mock_llm = self._llm_mock("direct", "ok")
        with patch("src.agents.agents.llm", mock_llm):
            from src.agents.graph import graph
            result = graph.invoke(
                {"question": "test", "messages": []},
                config={"configurable": {"thread_id": "cp01_user"}},
            )
        assert result is not None

    def test_CP02_different_thread_ids_isolated(self):
        mock_llm = self._llm_mock("direct", "answer_a", "direct", "answer_b")
        from src.agents.graph import graph
        with patch("src.agents.agents.llm", mock_llm):
            result_a = graph.invoke(
                {"question": "q_a", "messages": []},
                config={"configurable": {"thread_id": "cp02_user_a"}},
            )
            result_b = graph.invoke(
                {"question": "q_b", "messages": []},
                config={"configurable": {"thread_id": "cp02_user_b"}},
            )
        assert result_a.get("answer") != result_b.get("answer")

    def test_CP03_same_thread_id_accumulates_state(self):
        mock_llm = self._llm_mock("direct", "first answer", "direct", "second answer")
        from src.agents.graph import graph
        with patch("src.agents.agents.llm", mock_llm):
            config = {"configurable": {"thread_id": "cp03_same_user"}}
            graph.invoke({"question": "first", "messages": []}, config=config)
            graph.invoke({"question": "second", "messages": []}, config=config)
        assert mock_llm.invoke.call_count == 4


# ---------------------------------------------------------------------------
# E2E — End-to-end workflow with mocked LLM and tools
# ---------------------------------------------------------------------------

class TestEndToEndWorkflow:
    def _llm_mock(self, *contents):
        mock = MagicMock()
        mock.invoke.side_effect = [MagicMock(content=c) for c in contents]
        return mock

    def test_E2E01_vector_route(self):
        mock_llm = self._llm_mock("vector", "vector answer")
        mock_vs = MagicMock()
        mock_vs.invoke.return_value = "vector data"
        with patch("src.agents.agents.llm", mock_llm), \
             patch("src.agents.agents.vector_search", mock_vs):
            from src.agents.graph import graph
            result = graph.invoke(
                {"question": "test question", "messages": []},
                config={"configurable": {"thread_id": "e2e_vector_user"}},
            )
        assert result.get("answer") == "vector answer"

    def test_E2E02_kg_route(self):
        mock_llm = self._llm_mock("kg", "kg answer")
        mock_gs = MagicMock()
        mock_gs.invoke.return_value = "kg data"
        with patch("src.agents.agents.llm", mock_llm), \
             patch("src.agents.agents.graph_search", mock_gs):
            from src.agents.graph import graph
            result = graph.invoke(
                {"question": "test question", "messages": []},
                config={"configurable": {"thread_id": "e2e_kg_user"}},
            )
        assert result.get("answer") == "kg answer"

    def test_E2E03_direct_route(self):
        mock_llm = self._llm_mock("direct", "direct answer")
        with patch("src.agents.agents.llm", mock_llm):
            from src.agents.graph import graph
            result = graph.invoke(
                {"question": "test question", "messages": []},
                config={"configurable": {"thread_id": "e2e_direct_user"}},
            )
        assert result.get("answer") == "direct answer"

    def test_E2E04_both_route(self):
        mock_llm = self._llm_mock("both", "both answer")
        mock_vs = MagicMock()
        mock_vs.invoke.return_value = "vector data"
        mock_gs = MagicMock()
        mock_gs.invoke.return_value = "kg data"
        with patch("src.agents.agents.llm", mock_llm), \
             patch("src.agents.agents.vector_search", mock_vs), \
             patch("src.agents.agents.graph_search", mock_gs):
            from src.agents.graph import graph
            result = graph.invoke(
                {"question": "test both", "messages": []},
                config={"configurable": {"thread_id": "e2e_both_user"}},
            )
        assert result.get("answer") == "both answer"
        assert result.get("vector_result") == "vector data"
        assert result.get("kg_result") == "kg data"
