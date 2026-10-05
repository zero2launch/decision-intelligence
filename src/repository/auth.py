import logging

from src.db.mongo_connection import MongoDBConnection

logger = logging.getLogger(__name__)


class AuthRepository:

    @property
    def _collection(self):
        return MongoDBConnection.get_collection("users")

    def find_by_username(self, username: str) -> dict | None:
        logger.info(f"Finding user by username: {username}")
        return self._collection.find_one({"username": username})

    def insert_user(self, document: dict) -> str:
        logger.info("Inserting new user document")
        result = self._collection.insert_one(document)
        return str(result.inserted_id)
