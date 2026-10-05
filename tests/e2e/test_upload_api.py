import base64
import os
from pathlib import Path

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
def reset_collections():
    if MongoDBConnection._db is None or MongoDBConnection._db.name != TEST_DB:
        MongoDBConnection.close()
        MongoDBConnection._client = None
        MongoDBConnection._db = None
        MongoDBConnection.connect("mongodb://root:example@localhost:27017/?authSource=admin", TEST_DB)
    yield
    MongoDBConnection.get_collection("users").drop()
    MongoDBConnection.get_collection("documents").drop()
    MongoDBConnection.get_collection("parent_chunks").drop()


@pytest.fixture
def auth_token():
    response = client.post("/api/signup", json={"username": "testuser", "password": "testpassword1"})
    assert response.status_code == 201
    return response.json()["token"]


def _upload(files_payload: list, token: str | None) -> object:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/upload", json={"files": files_payload}, headers=headers)


def test_valid_pdf_upload(auth_token, minimal_pdf_b64):
    response = _upload(
        [{"filename": "report.pdf", "content": minimal_pdf_b64, "size": 1000}],
        auth_token,
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "uploaded": 1}


def test_valid_csv_upload(auth_token, minimal_csv_b64):
    response = _upload(
        [{"filename": "data.csv", "content": minimal_csv_b64, "size": 15}],
        auth_token,
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "uploaded": 1}


def test_valid_xlsx_upload(auth_token, minimal_xlsx_b64):
    response = _upload(
        [{"filename": "data.xlsx", "content": minimal_xlsx_b64, "size": 500}],
        auth_token,
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "uploaded": 1}


def test_multiple_mixed_files(auth_token, minimal_pdf_b64, minimal_csv_b64):
    response = _upload(
        [
            {"filename": "report.pdf", "content": minimal_pdf_b64, "size": 1000},
            {"filename": "data.csv", "content": minimal_csv_b64, "size": 15},
        ],
        auth_token,
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "uploaded": 2}


def test_missing_authorization_header(minimal_csv_b64):
    response = _upload(
        [{"filename": "data.csv", "content": minimal_csv_b64, "size": 15}],
        token=None,
    )
    assert response.status_code == 401
    assert response.json() == {"success": False, "error": "Invalid or expired token"}


def test_invalid_token(minimal_csv_b64):
    response = _upload(
        [{"filename": "data.csv", "content": minimal_csv_b64, "size": 15}],
        token="bad-token",
    )
    assert response.status_code == 401
    assert response.json() == {"success": False, "error": "Invalid or expired token"}


def test_empty_files_list(auth_token):
    response = client.post(
        "/api/upload",
        json={"files": []},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 422


def test_unsupported_file_type(auth_token, minimal_csv_b64):
    response = _upload(
        [{"filename": "notes.txt", "content": minimal_csv_b64, "size": 15}],
        auth_token,
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert "Unsupported file type" in body["error"]
    assert "notes.txt" in body["error"]


def test_malformed_base64(auth_token):
    response = _upload(
        [{"filename": "data.csv", "content": "!!!", "size": 15}],
        auth_token,
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert "Invalid Base64 content" in body["error"]


def test_valid_xls_upload(auth_token, minimal_xls_b64):
    response = _upload(
        [{"filename": "data.xls", "content": minimal_xls_b64, "size": 500}],
        auth_token,
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "uploaded": 1}


def test_upload_document_persisted_in_db(auth_token, minimal_csv_b64):
    _upload(
        [{"filename": "data.csv", "content": minimal_csv_b64, "size": 15}],
        auth_token,
    )
    count = MongoDBConnection.get_collection("documents").count_documents({"username": "testuser"})
    assert count == 1


@pytest.fixture
def clean_neo4j():
    from src.db.neo4j_connection import Neo4jConnection
    yield
    with Neo4jConnection.get_session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def test_full_rag_and_kg_pipeline(auth_token, clean_neo4j):
    datasets_root = Path(__file__).parent.parent.parent / "datasets"
    pdf_path = datasets_root / "proposal_documents" / "proposal_001.pdf"
    csv_path = datasets_root / "crm_exports" / "opportunities.csv"

    pdf_b64 = base64.b64encode(pdf_path.read_bytes()).decode()
    csv_b64 = base64.b64encode(csv_path.read_bytes()).decode()

    # PDF: RAG (chunking → MongoDB + ChromaDB) and KG (LLM extraction → Neo4j) run in parallel
    pdf_response = _upload(
        [{"filename": pdf_path.name, "content": pdf_b64, "size": pdf_path.stat().st_size}],
        auth_token,
    )
    assert pdf_response.status_code == 200
    assert pdf_response.json() == {"success": True, "uploaded": 1}

    # CSV: KG pipeline only (LLM extraction → Neo4j)
    csv_response = _upload(
        [{"filename": csv_path.name, "content": csv_b64, "size": csv_path.stat().st_size}],
        auth_token,
    )
    assert csv_response.status_code == 200
    assert csv_response.json() == {"success": True, "uploaded": 1}

    # RAG — parent chunks must be persisted in MongoDB for the PDF
    chunk_count = MongoDBConnection.get_collection("parent_chunks").count_documents(
        {"filename": pdf_path.name, "username": "testuser"}
    )
    assert chunk_count >= 1

    # RAG — child chunk embeddings must be stored in ChromaDB, keyed by filename metadata
    from src.db.chroma_connection import ChromaConnection
    chroma_result = ChromaConnection.get_collection().get(where={"filename": pdf_path.name})
    assert len(chroma_result["ids"]) >= 1

    # KG — Neo4j must contain at least one node extracted from either file
    from src.db.neo4j_connection import Neo4jConnection
    with Neo4jConnection.get_session() as session:
        record = session.run("MATCH (n) RETURN count(n) AS cnt").single()
    assert record["cnt"] >= 1


def test_accounts_csv_creates_kg_nodes(auth_token, clean_neo4j):
    """accounts.csv must produce Account, Industry, and Region nodes in Neo4j.

    Regression: the LLM was hallucinating Account.tier from the industry column (e.g.
    setting tier='Healthcare'), which is not in the allowed enum [Enterprise|Mid-Market|
    Government], causing _validate() to drop every Account node.  The system prompt now
    explicitly forbids inferring enum fields from other columns.
    """
    from src.db.neo4j_connection import Neo4jConnection

    datasets_root = Path(__file__).parent.parent.parent / "datasets"
    csv_path = datasets_root / "crm_exports" / "accounts.csv"

    csv_b64 = base64.b64encode(csv_path.read_bytes()).decode()
    response = _upload(
        [{"filename": csv_path.name, "content": csv_b64, "size": csv_path.stat().st_size}],
        auth_token,
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "uploaded": 1}

    with Neo4jConnection.get_session() as session:
        account_cnt = session.run("MATCH (n:Account) RETURN count(n) AS cnt").single()["cnt"]
        industry_cnt = session.run("MATCH (n:Industry) RETURN count(n) AS cnt").single()["cnt"]
        region_cnt = session.run("MATCH (n:Region) RETURN count(n) AS cnt").single()["cnt"]

    assert account_cnt >= 1, (
        f"Expected Account nodes in Neo4j but got 0 — LLM may be hallucinating invalid "
        f"tier values from the industry column and getting all accounts dropped by _validate()"
    )
    assert industry_cnt >= 1, f"Expected Industry nodes in Neo4j but got 0"
    assert region_cnt >= 1, f"Expected Region nodes in Neo4j but got 0"


def test_kg_repository_log_message_is_ascii_safe(caplog):
    """Regression: relationship_exists must not emit non-ASCII characters (e.g. → U+2192).

    The original bug: the log message used → which the Windows cp1252 console stream
    cannot encode, causing a UnicodeEncodeError inside logging.StreamHandler.emit().
    """
    import logging
    from unittest.mock import MagicMock, patch

    from src.db.neo4j_connection import Neo4jConnection
    from src.repository.knowledge_graph import KnowledgeGraphRepository

    mock_driver = MagicMock()
    mock_session = mock_driver.session.return_value.__enter__.return_value
    mock_session.run.return_value.single.return_value = {"cnt": 0}

    repo = KnowledgeGraphRepository()
    with patch.object(Neo4jConnection, "get_driver", return_value=mock_driver):
        with caplog.at_level(logging.INFO, logger="src.repository.knowledge_graph"):
            repo.relationship_exists(
                "Deal", "deal_id", "D001",
                "Region", "name", "APAC",
                "IN_REGION",
            )

    assert caplog.records, "Expected at least one log record from relationship_exists"
    for record in caplog.records:
        msg = record.getMessage()
        try:
            msg.encode("ascii")
        except UnicodeEncodeError:
            pytest.fail(f"Non-ASCII character in log message — would crash cp1252 stream: {msg!r}")


def test_console_log_handler_handles_non_ascii_without_error():
    """Regression: root console StreamHandler must not raise UnicodeEncodeError for non-ASCII chars.

    Verifies that setup_logging() wraps the stream with errors='backslashreplace' so that
    characters outside the console's codec (e.g. → on cp1252) are escaped, not crash-logged.
    """
    import logging

    root = logging.getLogger()
    console_handlers = [
        h for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    assert console_handlers, "No console StreamHandler on root logger"
    handler = console_handlers[0]

    handle_error_called = []
    original_handle_error = handler.handleError

    def _capture_error(record):
        handle_error_called.append(True)
        original_handle_error(record)

    handler.handleError = _capture_error
    try:
        bad_record = logging.LogRecord(
            name="test.unicode",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Relationship check: A → B",
            args=(),
            exc_info=None,
        )
        handler.emit(bad_record)
    finally:
        handler.handleError = original_handle_error

    assert not handle_error_called, (
        "StreamHandler.handleError was triggered — the console handler cannot encode \\u2192; "
        "setup_logging() must wrap stderr with errors='backslashreplace'"
    )
