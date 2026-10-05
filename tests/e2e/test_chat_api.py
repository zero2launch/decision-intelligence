import os

os.environ["MONGO_URI"] = "mongodb://root:example@localhost:27017/?authSource=admin"
os.environ["DATABASE_NAME"] = "test_decision_intelligence_db"
os.environ["JWT_SECRET"] = "test_secret_key_minimum_32_characters_xxxx"
os.environ["JWT_EXPIRES_IN"] = "3600"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["OPENAI_API_KEY"] = "sk-test-placeholder"

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.db.mongo_connection import MongoDBConnection
from src.main import app

TEST_DB = "test_decision_intelligence_db"

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_users_collection():
    if MongoDBConnection._db is None or MongoDBConnection._db.name != TEST_DB:
        MongoDBConnection.close()
        MongoDBConnection._client = None
        MongoDBConnection._db = None
        MongoDBConnection.connect("mongodb://root:example@localhost:27017/?authSource=admin", TEST_DB)
    yield
    MongoDBConnection.get_collection("users").drop()


@pytest.fixture(scope="module")
def auth_token():
    client.post("/api/signup", json={"username": "chatuser", "password": "Pass123!"})
    resp = client.post("/api/login", json={"username": "chatuser", "password": "Pass123!"})
    return resp.json()["token"]


@pytest.fixture(scope="module")
def alice_token():
    client.post("/api/signup", json={"username": "alice_chat", "password": "Pass123!"})
    resp = client.post("/api/login", json={"username": "alice_chat", "password": "Pass123!"})
    return resp.json()["token"]


@pytest.fixture(scope="module")
def bob_token():
    client.post("/api/signup", json={"username": "bob_chat", "password": "Pass123!"})
    resp = client.post("/api/login", json={"username": "bob_chat", "password": "Pass123!"})
    return resp.json()["token"]


def _make_graph_mock(answer: str):
    mock = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock.invoke.return_value = {"answer": answer}
    return mock


class TestChatApi:
    def test_E2E01_valid_question_returns_answer(self, auth_token):
        with patch("src.services.chat.graph") as mock_graph:
            mock_graph.invoke.return_value = {"answer": "Customer A bought Samsung."}
            resp = client.post(
                "/api/chat",
                json={"question": "Who bought Samsung?"},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"answer": "Customer A bought Samsung."}

    def test_E2E02_answer_reflects_graph_output(self, auth_token):
        with patch("src.services.chat.graph") as mock_graph:
            mock_graph.invoke.return_value = {"answer": "Custom answer."}
            resp = client.post(
                "/api/chat",
                json={"question": "Any question?"},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"answer": "Custom answer."}

    def test_E2E03_missing_authorization_header_returns_401(self):
        resp = client.post("/api/chat", json={"question": "test"})
        assert resp.status_code == 401
        assert resp.json() == {"success": False, "error": "Invalid or expired token"}

    def test_E2E04_invalid_bearer_token_returns_401(self):
        resp = client.post(
            "/api/chat",
            json={"question": "test"},
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
        assert resp.json() == {"success": False, "error": "Invalid or expired token"}

    def test_E2E05_non_bearer_scheme_returns_401(self):
        resp = client.post(
            "/api/chat",
            json={"question": "test"},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401
        assert resp.json() == {"success": False, "error": "Invalid or expired token"}

    def test_E2E06_empty_question_returns_422(self, auth_token):
        resp = client.post(
            "/api/chat",
            json={"question": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 422

    def test_E2E07_missing_question_field_returns_422(self, auth_token):
        resp = client.post(
            "/api/chat",
            json={},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 422

    def test_E2E08_graph_failure_returns_500(self, auth_token):
        with patch("src.services.chat.graph") as mock_graph:
            mock_graph.invoke.side_effect = Exception("graph error")
            resp = client.post(
                "/api/chat",
                json={"question": "test"},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 500
        assert resp.json() == {"success": False, "error": "Chat workflow failed"}

    def test_E2E09_different_users_produce_isolated_thread_ids(self, alice_token, bob_token):
        thread_ids = []

        def capture_invoke(input_dict, config):
            thread_ids.append(config["configurable"]["thread_id"])
            return {"answer": "ok"}

        with patch("src.services.chat.graph") as mock_graph:
            mock_graph.invoke.side_effect = capture_invoke
            resp_alice = client.post(
                "/api/chat",
                json={"question": "Alice's question"},
                headers={"Authorization": f"Bearer {alice_token}"},
            )
            resp_bob = client.post(
                "/api/chat",
                json={"question": "Bob's question"},
                headers={"Authorization": f"Bearer {bob_token}"},
            )

        assert resp_alice.status_code == 200
        assert resp_bob.status_code == 200
        assert len(thread_ids) == 2
        assert thread_ids[0] != thread_ids[1]
