import os

os.environ["MONGO_URI"] = "mongodb://root:example@localhost:27017/?authSource=admin"
os.environ["DATABASE_NAME"] = "test_decision_intelligence_db"
os.environ["JWT_SECRET"] = "test_secret_key_minimum_32_characters_xxxx"
os.environ["JWT_EXPIRES_IN"] = "3600"
os.environ["JWT_ALGORITHM"] = "HS256"

import pytest
from fastapi.testclient import TestClient

from src.db.mongo_connection import MongoDBConnection
from src.main import app

TEST_DB = "test_decision_intelligence_db"

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_users_collection():
    # Ensure we're on the test DB before each test
    if MongoDBConnection._db is None or MongoDBConnection._db.name != TEST_DB:
        MongoDBConnection.close()
        MongoDBConnection._client = None
        MongoDBConnection._db = None
        MongoDBConnection.connect("mongodb://root:example@localhost:27017/?authSource=admin", TEST_DB)
    yield
    MongoDBConnection.get_collection("users").drop()


def test_valid_signup():
    response = client.post("/api/signup", json={"username": "alice", "password": "securepass1"})
    assert response.status_code == 201
    body = response.json()
    assert "token" in body
    assert body["token"] != ""


def test_duplicate_username():
    client.post("/api/signup", json={"username": "alice", "password": "securepass1"})
    response = client.post("/api/signup", json={"username": "alice", "password": "securepass1"})
    assert response.status_code == 409
    assert response.json() == {"success": False, "error": "Username already taken"}


def test_short_username():
    response = client.post("/api/signup", json={"username": "ab", "password": "securepass1"})
    assert response.status_code == 422


def test_short_password():
    response = client.post("/api/signup", json={"username": "alice", "password": "short"})
    assert response.status_code == 422


def test_missing_field():
    response = client.post("/api/signup", json={"username": "alice"})
    assert response.status_code == 422
