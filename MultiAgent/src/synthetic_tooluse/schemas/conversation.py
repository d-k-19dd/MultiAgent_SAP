from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ToolCallRequest(BaseModel):
    endpoint: str
    arguments: Dict[str, Any]

class Message(BaseModel):
    role: str # user, assistant, tool
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCallRequest]] = None

class ConversationRecord(BaseModel):
    conversation_id: str
    messages: List[Message] = Field(default_factory=list)
    judge_scores: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
