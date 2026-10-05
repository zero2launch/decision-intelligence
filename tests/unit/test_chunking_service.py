import json
import uuid
from unittest.mock import MagicMock, call, patch

import pymongo.errors
import pytest

from src.services.chunking import ChunkingService
from src.utils.exception import AppException


@pytest.fixture()
def service():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        svc = ChunkingService.__new__(ChunkingService)
        svc._repo = MagicMock()
        svc._openai_api_key = "test-key"
        return svc


# --- _split_by_tokens ---

def test_split_by_tokens_splits_correctly(service):
    long_text = "hello world " * 400  # ~800 tokens
    chunks = service._split_by_tokens(long_text, 500)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert service._count_tokens(chunk) <= 500


def test_split_by_tokens_short_text_returns_single_chunk(service):
    short_text = "hello " * 10  # ~20 tokens
    chunks = service._split_by_tokens(short_text, 500)
    assert len(chunks) == 1
    assert short_text.strip() in chunks[0] or chunks[0].strip() in short_text.strip()


def test_split_by_tokens_empty_text_returns_empty(service):
    assert service._split_by_tokens("", 500) == []


def test_split_by_tokens_whitespace_only_returns_empty(service):
    assert service._split_by_tokens("   \n  ", 500) == []


# --- _count_tokens ---

def test_count_tokens_accuracy(service):
    assert service._count_tokens("hello world") == 2


# --- chunk_and_store ---

def _make_embedding():
    return [0.1] * 1536


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_happy_path(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection
    service._repo.insert_parent_chunk.return_value = "abc123"

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        result = service.chunk_and_store("hello world " * 10, "test.pdf", "alice")

    assert result > 0
    assert service._repo.insert_parent_chunk.call_count >= 1
    assert mock_collection.add.call_count == result


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_mongodb_error_raises_app_exception(mock_chroma, service):
    mock_chroma.get_collection.return_value = MagicMock()
    service._repo.insert_parent_chunk.side_effect = pymongo.errors.PyMongoError("db down")

    with pytest.raises(AppException) as exc_info:
        service.chunk_and_store("hello world " * 10, "test.pdf", "alice")

    assert exc_info.value.status_code == 500


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_openai_error_raises_app_exception(mock_chroma, service):
    mock_chroma.get_collection.return_value = MagicMock()
    service._repo.insert_parent_chunk.return_value = "abc123"

    with patch.object(service, "_generate_embedding", side_effect=Exception("rate limit")):
        with pytest.raises(AppException) as exc_info:
            service.chunk_and_store("hello world " * 10, "test.pdf", "alice")

    assert exc_info.value.status_code == 500


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_chromadb_error_raises_app_exception(mock_chroma, service):
    mock_collection = MagicMock()
    mock_collection.add.side_effect = Exception("chroma error")
    mock_chroma.get_collection.return_value = mock_collection
    service._repo.insert_parent_chunk.return_value = "abc123"

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        with pytest.raises(AppException) as exc_info:
            service.chunk_and_store("hello world " * 10, "test.pdf", "alice")

    assert exc_info.value.status_code == 500


# --- _format_row_as_text ---

def test_format_row_as_text_normal_row(service):
    assert service._format_row_as_text({"Name": "Alice", "Age": 30}) == "Name: Alice | Age: 30"


def test_format_row_as_text_omits_none(service):
    assert service._format_row_as_text({"Name": "Alice", "Score": None}) == "Name: Alice"


def test_format_row_as_text_empty_dict(service):
    assert service._format_row_as_text({}) == ""


# --- chunk_and_store_tabular ---

def _make_rows(n: int) -> list[dict]:
    return [{"Product": f"Item{i}", "Value": i * 10} for i in range(n)]


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_happy_path_25_rows(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        result = service.chunk_and_store_tabular(json.dumps(_make_rows(25)), "data.csv", "alice")

    assert result == 3
    assert mock_collection.add.call_count == 3


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_exact_multiple(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        result = service.chunk_and_store_tabular(json.dumps(_make_rows(20)), "data.csv", "alice")

    assert result == 2
    assert mock_collection.add.call_count == 2


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_empty_rows(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding") as mock_embed:
        result = service.chunk_and_store_tabular("[]", "empty.csv", "alice")

    assert result == 0
    mock_embed.assert_not_called()
    mock_collection.add.assert_not_called()


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_single_row(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        result = service.chunk_and_store_tabular(json.dumps(_make_rows(1)), "data.csv", "alice")

    assert result == 1
    assert mock_collection.add.call_count == 1
    metadata = mock_collection.add.call_args[1]["metadatas"][0]
    assert metadata["row_start"] == 0
    assert metadata["row_end"] == 0


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_metadata_shape(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        service.chunk_and_store_tabular(json.dumps(_make_rows(15)), "data.csv", "alice")

    assert mock_collection.add.call_count == 2
    second_call_meta = mock_collection.add.call_args_list[1][1]["metadatas"][0]
    assert second_call_meta["chunk_index"] == 1
    assert second_call_meta["row_start"] == 10
    assert second_call_meta["row_end"] == 14


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_openai_error(mock_chroma, service):
    mock_chroma.get_collection.return_value = MagicMock()

    with patch.object(service, "_generate_embedding", side_effect=Exception("timeout")):
        with pytest.raises(AppException) as exc_info:
            service.chunk_and_store_tabular(json.dumps(_make_rows(5)), "data.csv", "alice")

    assert exc_info.value.status_code == 500


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_chromadb_error(mock_chroma, service):
    mock_collection = MagicMock()
    mock_collection.add.side_effect = Exception("chroma error")
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        with pytest.raises(AppException) as exc_info:
            service.chunk_and_store_tabular(json.dumps(_make_rows(5)), "data.csv", "alice")

    assert exc_info.value.status_code == 500


@patch("src.services.chunking.ChromaConnection")
def test_chunk_and_store_tabular_uuid_ids_unique(mock_chroma, service):
    mock_collection = MagicMock()
    mock_chroma.get_collection.return_value = mock_collection

    with patch.object(service, "_generate_embedding", return_value=_make_embedding()):
        service.chunk_and_store_tabular(json.dumps(_make_rows(20)), "data.csv", "alice")

    assert mock_collection.add.call_count == 2
    id_0 = mock_collection.add.call_args_list[0][1]["ids"][0]
    id_1 = mock_collection.add.call_args_list[1][1]["ids"][0]
    uuid.UUID(id_0)  # raises ValueError if not a valid UUID
    uuid.UUID(id_1)
    assert id_0 != id_1
