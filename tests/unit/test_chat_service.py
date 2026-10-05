import os
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
from unittest.mock import MagicMock, patch
from src.services.chat import ChatService
from src.utils.exception import AppException


@pytest.fixture()
def service():
    return ChatService()


@pytest.fixture()
def mock_graph():
    with patch("src.services.chat.graph") as mock:
        yield mock


class TestChatService:
    def test_CS01_returns_answer_from_graph_result(self, service, mock_graph):
        mock_graph.invoke.return_value = {"answer": "Here is the answer."}
        assert service.ask("q", "alice") == "Here is the answer."

    def test_CS02_passes_question_in_graph_input(self, service, mock_graph):
        mock_graph.invoke.return_value = {"answer": "ok"}
        service.ask("q", "alice")
        call_args = mock_graph.invoke.call_args
        input_dict = call_args[0][0]
        assert input_dict.get("question") == "q"

    def test_CS03_sets_thread_id_from_username(self, service, mock_graph):
        mock_graph.invoke.return_value = {"answer": "ok"}
        service.ask("q", "alice")
        call_kwargs = mock_graph.invoke.call_args[1]
        assert call_kwargs["config"] == {"configurable": {"thread_id": "alice"}}

    def test_CS04_different_usernames_produce_different_thread_ids(self, service, mock_graph):
        mock_graph.invoke.return_value = {"answer": "ok"}
        service.ask("q", "alice")
        first_config = mock_graph.invoke.call_args[1]["config"]

        service.ask("q", "bob")
        second_config = mock_graph.invoke.call_args[1]["config"]

        assert first_config["configurable"]["thread_id"] == "alice"
        assert second_config["configurable"]["thread_id"] == "bob"

    def test_CS05_graph_exception_raises_app_exception_500(self, service, mock_graph):
        mock_graph.invoke.side_effect = Exception("LLM error")
        with pytest.raises(AppException) as exc_info:
            service.ask("q", "alice")
        assert exc_info.value.status_code == 500
        assert exc_info.value.message == "Chat workflow failed"

    def test_CS06_empty_answer_raises_app_exception_500(self, service, mock_graph):
        mock_graph.invoke.return_value = {"answer": ""}
        with pytest.raises(AppException) as exc_info:
            service.ask("q", "alice")
        assert exc_info.value.status_code == 500

    def test_CS07_missing_answer_key_raises_app_exception_500(self, service, mock_graph):
        mock_graph.invoke.return_value = {}
        with pytest.raises(AppException) as exc_info:
            service.ask("q", "alice")
        assert exc_info.value.status_code == 500

    def test_CS08_app_exception_from_graph_re_raised_as_500(self, service, mock_graph):
        mock_graph.invoke.side_effect = AppException("downstream error", 400)
        with pytest.raises(AppException) as exc_info:
            service.ask("q", "alice")
        assert exc_info.value.status_code == 500
