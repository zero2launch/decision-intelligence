import logging

from src.db.mongo_connection import MongoDBConnection

logger = logging.getLogger(__name__)


class ChunkRepository:

    @property
    def _collection(self):
        return MongoDBConnection.get_collection("parent_chunks")

    def find_parent_chunks_by_ids(self, parent_ids: list[str]) -> list[dict]:
        """Fetch parent chunk documents from MongoDB by their string IDs."""
        from bson import ObjectId
        logger.info(f"Fetching {len(parent_ids)} parent chunk(s) by ID")
        if not parent_ids:
            return []
        object_ids = [ObjectId(pid) for pid in parent_ids]
        return list(self._collection.find({"_id": {"$in": object_ids}}))

    def insert_parent_chunk(self, document: dict) -> str:
        logger.info(
            f"Inserting parent chunk index={document.get('chunk_index')} "
            f"for file={document.get('filename')}"
        )
        result = self._collection.insert_one(document)
        return str(result.inserted_id)
