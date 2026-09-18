from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=16000)


class Chat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["org-balanced", "org-economy", "mock-text-v1"] = "org-balanced"
    messages: list[Message] = Field(min_length=1, max_length=32)
    max_tokens: int = Field(default=128, ge=1, le=4096)
    stream: bool = False
    mock_fault: Literal["none", "before_dispatch", "timeout", "partial_stream"] = "none"
