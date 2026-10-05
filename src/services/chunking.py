import json
import logging
import os
import uuid
from datetime import datetime, timezone

import pymongo.errors

from src.db.chroma_connection import ChromaConnection
from src.repository.chunks import ChunkRepository
from src.schemas.chunks import ParentChunkDocument
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

PARENT_TOKEN_LIMIT = 500
CHILD_TOKEN_LIMIT = 100


class ChunkingService:
    def __init__(self):
        self._repo = ChunkRepository()
        self._openai_api_key = os.environ["OPENAI_API_KEY"]

    def chunk_and_store(self, text: str, filename: str, username: str) -> int:
        parent_chunks = self._split_by_tokens(text, PARENT_TOKEN_LIMIT)
        logger.info(f"Splitting '{filename}' into {len(parent_chunks)} parent chunks")

        total_children = 0
        chroma_collection = ChromaConnection.get_collection()

        for p_idx, parent_text in enumerate(parent_chunks):
            parent_doc = ParentChunkDocument(
                filename=filename,
                username=username,
                chunk_index=p_idx,
                text=parent_text,
                token_count=self._count_tokens(parent_text),
                created_at=datetime.now(timezone.utc),
            )
            try:
                parent_id = self._repo.insert_parent_chunk(parent_doc.to_dict())
            except pymongo.errors.PyMongoError as e:
                logger.error(f"DB error inserting parent chunk {p_idx} for '{filename}': {e}")
                raise AppException("Internal server error", status_code=500)

            child_chunks = self._split_by_tokens(parent_text, CHILD_TOKEN_LIMIT)
            logger.info(
                f"Parent chunk {p_idx} of '{filename}' split into {len(child_chunks)} child chunks"
            )

            for c_idx, child_text in enumerate(child_chunks):
                try:
                    embedding = self._generate_embedding(child_text)
                except Exception as e:
                    logger.error(f"OpenAI embedding error for child {c_idx} of parent {p_idx}: {e}")
                    raise AppException("Internal server error", status_code=500)

                try:
                    chroma_collection.add(
                        ids=[f"{parent_id}_{c_idx}"],
                        embeddings=[embedding],
                        documents=[child_text],
                        metadatas=[{
                            "parent_id": parent_id,
                            "filename": filename,
                            "username": username,
                            "child_index": c_idx,
                        }],
                    )
                except Exception as e:
                    logger.error(f"ChromaDB add error for child {c_idx} of parent {p_idx}: {e}")
                    raise AppException("Internal server error", status_code=500)

                total_children += 1

        logger.info(
            f"chunk_and_store complete for '{filename}': "
            f"{len(parent_chunks)} parents, {total_children} children stored"
        )
        return total_children

    def _split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        token_ids = enc.encode(text)
        chunks = []
        for start in range(0, len(token_ids), max_tokens):
            chunk_ids = token_ids[start : start + max_tokens]
            chunks.append(enc.decode(chunk_ids))
        return [c for c in chunks if c.strip()]

    def _count_tokens(self, text: str) -> int:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    def _generate_embedding(self, text: str) -> list[float]:
        from openai import OpenAI
        client = OpenAI(api_key=self._openai_api_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    def _format_row_as_text(self, row: dict) -> str:
        return " | ".join(f"{key}: {value}" for key, value in row.items() if value is not None)

    def chunk_and_store_tabular(self, rows_json: str, filename: str, username: str) -> int:
        rows: list[dict] = json.loads(rows_json)
        if not rows:
            logger.warning(f"No rows found in '{filename}' — skipping tabular chunking")
            return 0

        chroma_collection = ChromaConnection.get_collection()
        chunk_size = 10
        total_chunks = 0

        for chunk_index in range(0, len(rows), chunk_size):
            batch = rows[chunk_index : chunk_index + chunk_size]
            row_start = chunk_index
            row_end = chunk_index + len(batch) - 1

            chunk_text = "\n".join(self._format_row_as_text(row) for row in batch)

            try:
                embedding = self._generate_embedding(chunk_text)
            except Exception as e:
                logger.error(
                    f"OpenAI embedding error for chunk {chunk_index // chunk_size} "
                    f"of '{filename}': {e}"
                )
                raise AppException("Internal server error", status_code=500)

            chunk_id = str(uuid.uuid4())

            try:
                chroma_collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk_text],
                    metadatas=[{
                        "filename": filename,
                        "username": username,
                        "chunk_index": chunk_index // chunk_size,
                        "row_start": row_start,
                        "row_end": row_end,
                    }],
                )
            except Exception as e:
                logger.error(
                    f"ChromaDB add error for chunk {chunk_index // chunk_size} "
                    f"of '{filename}': {e}"
                )
                raise AppException("Internal server error", status_code=500)

            total_chunks += 1

        logger.info(
            f"chunk_and_store_tabular complete for '{filename}': "
            f"{total_chunks} chunks stored ({len(rows)} rows total)"
        )
        return total_chunks
