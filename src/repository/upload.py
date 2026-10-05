import logging

from src.db.mongo_connection import MongoDBConnection

logger = logging.getLogger(__name__)


class UploadRepository:

    @property
    def _collection(self):
        return MongoDBConnection.get_collection("documents")

    def insert_document(self, document: dict) -> str:
        logger.info(f"Inserting document: {document.get('filename')}")
        result = self._collection.insert_one(document)
        return str(result.inserted_id)
