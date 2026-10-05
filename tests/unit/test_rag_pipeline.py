import os
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
from unittest.mock import MagicMock, patch
from src.agents.rag_pipeline import _generate_query_embedding, run_vector_search
from src.utils.exception import AppException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def chroma_result_3():
    """Simulates ChromaDB returning 3 child chunks from 2 distinct parents."""
    return {
        "ids": [["aaa_0", "bbb_0", "aaa_1"]],
        "documents": [["child1", "child2", "child3"]],
        "metadatas": [[
            {"parent_id": "aaa", "filename": "f.pdf", "username": "u", "child_index": 0},
            {"parent_id": "bbb", "filename": "f.pdf", "username": "u", "child_index": 0},
            {"parent_id": "aaa", "filename": "f.pdf", "username": "u", "child_index": 1},
        ]],
        "distances": [[0.1, 0.2, 0.3]],
    }


@pytest.fixture()
def chroma_result_empty():
    return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture()
def parent_docs():
    return [
        {"_id": "aaa", "text": "Parent A text.", "chunk_index": 0},
        {"_id": "bbb", "text": "Parent B text.", "chunk_index": 0},
    ]


# ---------------------------------------------------------------------------
# GE — Embedding Generation (_generate_query_embedding)
# ---------------------------------------------------------------------------

class TestGenerateQueryEmbedding:

    def test_GE01_returns_list_of_floats(self):
        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.1, 0.2]
        with patch("src.agents.rag_pipeline.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            result = _generate_query_embedding("hello")
        assert isinstance(result, list)
        assert result == [0.1, 0.2]

    def test_GE02_uses_text_embedding_3_small_model(self):
        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.1]
        with patch("src.agents.rag_pipeline.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            _generate_query_embedding("hello")
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small", input="hello"
            )

    def test_GE03_passes_query_as_input(self):
        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.5]
        with patch("src.agents.rag_pipeline.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.return_value = mock_response
            _generate_query_embedding("test query")
            _, kwargs = mock_client.embeddings.create.call_args
            assert kwargs.get("input") == "test query" or mock_client.embeddings.create.call_args[1].get("input") == "test query" or mock_client.embeddings.create.call_args[0][1] == "test query"
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small", input="test query"
            )

    def test_GE04_reads_api_key_from_env(self):
        mock_response = MagicMock()
        mock_response.data[0].embedding = [0.1]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-xyz"}):
            with patch("src.agents.rag_pipeline.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_openai_cls.return_value = mock_client
                mock_client.embeddings.create.return_value = mock_response
                _generate_query_embedding("hello")
                mock_openai_cls.assert_called_once_with(api_key="sk-xyz")

    def test_GE05_openai_exception_raises_app_exception_500(self):
        with patch("src.agents.rag_pipeline.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.side_effect = Exception("quota exceeded")
            with pytest.raises(AppException) as exc_info:
                _generate_query_embedding("hello")
            assert exc_info.value.status_code == 500

    def test_GE06_app_exception_message_is_descriptive(self):
        with patch("src.agents.rag_pipeline.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.side_effect = Exception("quota exceeded")
            with pytest.raises(AppException) as exc_info:
                _generate_query_embedding("hello")
            assert "Embedding generation failed" in exc_info.value.message


# ---------------------------------------------------------------------------
# VS — Vector Search (run_vector_search)
# ---------------------------------------------------------------------------

class TestRunVectorSearch:

    def test_VS01_returns_non_empty_string_on_success(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            result = run_vector_search("some query")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_VS02_returned_string_contains_parent_chunk_text(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            result = run_vector_search("some query")
        assert "Parent A text." in result

    def test_VS03_multiple_parent_texts_are_concatenated(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            result = run_vector_search("some query")
        assert "Parent A text." in result
        assert "Parent B text." in result

    def test_VS04_texts_separated_by_double_newline(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            result = run_vector_search("some query")
        assert "\n\n" in result

    def test_VS05_returns_empty_string_when_chroma_returns_no_results(self, chroma_result_empty):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo"):
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_empty
            result = run_vector_search("some query")
        assert result == ""

    def test_VS06_generate_query_embedding_called_with_query(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]) as mock_embed, \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            run_vector_search("my query")
        mock_embed.assert_called_once_with("my query")

    def test_VS07_chroma_query_called_with_embedding(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1, 0.2]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_collection = mock_chroma.get_collection.return_value
            mock_collection.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            run_vector_search("some query")
        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2]], n_results=3
        )

    def test_VS08_chroma_query_requests_top_3_results(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.5]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_collection = mock_chroma.get_collection.return_value
            mock_collection.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            run_vector_search("some query")
        _, kwargs = mock_collection.query.call_args
        assert kwargs.get("n_results") == 3

    def test_VS09_duplicate_parent_ids_deduplicated(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            run_vector_search("some query")
        called_ids = mock_repo.find_parent_chunks_by_ids.call_args[0][0]
        assert called_ids.count("aaa") == 1

    def test_VS10_mongodb_not_called_when_chroma_empty(self, chroma_result_empty):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_empty
            run_vector_search("some query")
        mock_repo.find_parent_chunks_by_ids.assert_not_called()

    def test_VS11_all_unique_parent_ids_fetched(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            run_vector_search("some query")
        called_ids = mock_repo.find_parent_chunks_by_ids.call_args[0][0]
        assert len(called_ids) == 2

    def test_VS12_closest_match_parent_appears_first(self, chroma_result_3, parent_docs):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = parent_docs
            result = run_vector_search("some query")
        assert result.startswith("Parent A text.")

    def test_VS13_chroma_access_error_raises_app_exception_500(self):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo"):
            mock_chroma.get_collection.return_value.query.side_effect = Exception("chroma down")
            with pytest.raises(AppException) as exc_info:
                run_vector_search("some query")
        assert exc_info.value.status_code == 500

    def test_VS14_app_exception_from_embedding_propagates_unchanged(self):
        original = AppException("Embedding generation failed", status_code=500)
        with patch("src.agents.rag_pipeline._generate_query_embedding", side_effect=original), \
             patch("src.agents.rag_pipeline.ChromaConnection"), \
             patch("src.agents.rag_pipeline._repo"):
            with pytest.raises(AppException) as exc_info:
                run_vector_search("some query")
        assert exc_info.value is original

    def test_VS15_empty_parent_docs_produces_empty_string(self, chroma_result_3):
        with patch("src.agents.rag_pipeline._generate_query_embedding", return_value=[0.1]), \
             patch("src.agents.rag_pipeline.ChromaConnection") as mock_chroma, \
             patch("src.agents.rag_pipeline._repo") as mock_repo:
            mock_chroma.get_collection.return_value.query.return_value = chroma_result_3
            mock_repo.find_parent_chunks_by_ids.return_value = []
            result = run_vector_search("some query")
        assert result == ""


# ---------------------------------------------------------------------------
# FR — ChunkRepository.find_parent_chunks_by_ids
# ---------------------------------------------------------------------------

class TestFindParentChunksByIds:

    def _make_repo_with_mock_collection(self, mock_find_return):
        from src.repository.chunks import ChunkRepository
        repo = ChunkRepository()
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_find_return
        with patch.object(type(repo), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            yield repo, mock_collection

    @pytest.fixture()
    def mock_collection(self):
        return MagicMock()

    @pytest.fixture()
    def repo(self, mock_collection):
        from src.repository.chunks import ChunkRepository
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            yield r

    def test_FR01_returns_a_list(self, mock_collection):
        from src.repository.chunks import ChunkRepository
        mock_collection.find.return_value = [{"_id": "x", "text": "t"}] * 2
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            result = r.find_parent_chunks_by_ids(["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"])
        assert isinstance(result, list)

    def test_FR02_returns_all_matching_docs(self, mock_collection):
        from src.repository.chunks import ChunkRepository
        mock_collection.find.return_value = [{"_id": "x", "text": "t1"}, {"_id": "y", "text": "t2"}]
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            result = r.find_parent_chunks_by_ids(["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"])
        assert len(result) == 2

    def test_FR03_empty_parent_ids_returns_empty_list_immediately(self, mock_collection):
        from src.repository.chunks import ChunkRepository
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            result = r.find_parent_chunks_by_ids([])
        assert result == []
        mock_collection.find.assert_not_called()

    def test_FR04_uses_in_query_with_object_id_list(self, mock_collection):
        from bson import ObjectId
        from src.repository.chunks import ChunkRepository
        mock_collection.find.return_value = []
        valid_ids = ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"]
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            r.find_parent_chunks_by_ids(valid_ids)
        call_args = mock_collection.find.call_args[0][0]
        assert "$in" in call_args["_id"]
        assert all(isinstance(oid, ObjectId) for oid in call_args["_id"]["$in"])
        assert call_args["_id"]["$in"] == [ObjectId(i) for i in valid_ids]

    def test_FR05_single_id_works(self, mock_collection):
        from src.repository.chunks import ChunkRepository
        mock_collection.find.return_value = [{"_id": "x", "text": "only"}]
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            result = r.find_parent_chunks_by_ids(["507f1f77bcf86cd799439011"])
        assert len(result) == 1
        mock_collection.find.assert_called_once()

    def test_FR06_all_fetched_documents_are_returned(self, mock_collection):
        from src.repository.chunks import ChunkRepository
        mock_collection.find.return_value = [{"_id": str(i), "text": f"t{i}"} for i in range(3)]
        valid_ids = ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012", "507f1f77bcf86cd799439013"]
        r = ChunkRepository()
        with patch.object(type(r), "_collection", new_callable=lambda: property(lambda self: mock_collection)):
            result = r.find_parent_chunks_by_ids(valid_ids)
        assert len(result) == 3
