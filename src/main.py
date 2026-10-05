from src.logging.logger import setup_logging

setup_logging()

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from src.api.auth import auth_router
from src.api.chat import chat_router
from src.api.upload import upload_router
from src.db.chroma_connection import ChromaConnection
from src.db.mongo_connection import MongoDBConnection
from src.utils.exception import AppException, app_exception_handler

logger = logging.getLogger(__name__)

MongoDBConnection.connect(
    uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
    database_name=os.environ.get("DATABASE_NAME", "decision_intelligence_db"),
)

from pymongo import ASCENDING, DESCENDING

MongoDBConnection.get_collection("users").create_index([("username", ASCENDING)], unique=True)
MongoDBConnection.get_collection("documents").create_index(
    [("username", ASCENDING), ("uploaded_at", DESCENDING)]
)
MongoDBConnection.get_collection("parent_chunks").create_index(
    [("username", ASCENDING), ("filename", ASCENDING)]
)

ChromaConnection.initialize()

from src.db.neo4j_connection import Neo4jConnection

Neo4jConnection.connect(
    uri=os.environ.get("NEO4J_URL", "bolt://localhost:7687"),
    user=os.environ.get("NEO4J_USERNAME", "neo4j"),
    password=os.environ["NEO4J_PASSWORD"],
    database=os.environ.get("NEO4J_DATABASE", "neo4j"),
)

app = FastAPI(title="Decision Intelligence API")
app.add_exception_handler(AppException, app_exception_handler)
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
