from pydantic import BaseModel, Field


class MessageRecord(BaseModel):
    id: str
    user_id: str
    user_name: str
    timestamp: str
    message: str


class PaginatedMessages(BaseModel):
    total: int
    items: list[MessageRecord]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")


class AskMetadata(BaseModel):
    reasoning: str


class AskResponse(BaseModel):
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    sources: list[str]
    metadata: AskMetadata
