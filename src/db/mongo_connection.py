import logging

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from src.utils.exception import AppException

logger = logging.getLogger(__name__)

# Collections: users


class MongoDBConnection:
    _client: MongoClient | None = None
    _db: Database | None = None

    @classmethod
    def connect(cls, uri: str, database_name: str) -> None:
        if cls._client is not None:
            return
        cls._client = MongoClient(uri)
        cls._db = cls._client[database_name]
        logger.info(f"Connected to MongoDB database: {database_name}")

    @classmethod
    def get_collection(cls, name: str) -> Collection:
        if cls._db is None:
            raise AppException("Database not initialized. Call connect() first.", status_code=500)
        return cls._db[name]

    @classmethod
    def close(cls) -> None:
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            logger.info("MongoDB connection closed")
