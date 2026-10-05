import logging
import os

from openai import OpenAI

from src.db.chroma_connection import ChromaConnection
from src.repository.chunks import ChunkRepository
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

_repo = ChunkRepository()


def _generate_query_embedding(query: str) -> list[float]:
    """Embed a query string using OpenAI text-embedding-3-small."""
    try:
        api_key = os.environ["OPENAI_API_KEY"]
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model="text-embedding-3-small", input=query)
        return response.data[0].embedding
    except AppException:
        raise
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise AppException("Embedding generation failed", status_code=500)


def run_vector_search(query: str) -> str:
    """Orchestrate RAG retrieval. Return context string or '' if no results."""
    embedding = _generate_query_embedding(query)

    try:
        result = ChromaConnection.get_collection().query(
            query_embeddings=[embedding], n_results=3
        )
    except AppException:
        raise
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise AppException("Vector search failed", status_code=500)

    metadatas = result["metadatas"][0]
    if not metadatas:
        logger.warning("ChromaDB returned no results for query")
        return ""

    parent_ids = [m["parent_id"] for m in metadatas]
    unique_parent_ids = list(dict.fromkeys(parent_ids))

    docs = _repo.find_parent_chunks_by_ids(unique_parent_ids)
    return "\n\n".join(doc["text"] for doc in docs)
