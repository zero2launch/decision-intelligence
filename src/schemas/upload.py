from pydantic import BaseModel, Field


class UploadedFile(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str
    size: int = Field(ge=0)


class UploadRequest(BaseModel):
    files: list[UploadedFile] = Field(min_length=1)


class UploadResponse(BaseModel):
    success: bool
    uploaded: int
