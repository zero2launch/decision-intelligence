from dataclasses import dataclass
from datetime import datetime


@dataclass
class ParentChunkDocument:
    filename: str
    username: str
    chunk_index: int
    text: str
    token_count: int
    created_at: datetime

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "username": self.username,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "token_count": self.token_count,
            "created_at": self.created_at,
        }
