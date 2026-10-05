import logging

from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class Neo4jConnection:
    _driver = None
    _database: str = "neo4j"

    @classmethod
    def connect(cls, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        if cls._driver is not None:
            return
        from neo4j import GraphDatabase
        cls._driver = GraphDatabase.driver(uri, auth=(user, password))
        cls._database = database
        logger.info(f"Connected to Neo4j: {uri}, database={database}")

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            raise AppException("Neo4j not initialized. Call connect() first.", status_code=500)
        return cls._driver

    @classmethod
    def get_session(cls):
        return cls.get_driver().session(database=cls._database)

    @classmethod
    def close(cls) -> None:
        if cls._driver:
            cls._driver.close()
            cls._driver = None
            logger.info("Neo4j connection closed")
