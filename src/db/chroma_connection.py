import logging

from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class ChromaConnection:
    _client = None
    _collection = None

    @classmethod
    def initialize(cls, collection_name: str = "child_chunks") -> None:
        if cls._client is not None:
            return
        import chromadb
        cls._client = chromadb.Client()
        cls._collection = cls._client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB in-memory collection '{collection_name}' initialized")

    @classmethod
    def get_collection(cls):
        if cls._collection is None:
            raise AppException("ChromaDB not initialized. Call initialize() first.", status_code=500)
        return cls._collection
