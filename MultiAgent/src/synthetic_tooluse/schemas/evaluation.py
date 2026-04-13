from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class JudgeScores(BaseModel):
    naturalness: float = Field(ge=0.0, le=5.0)
    tool_correctness: float = Field(ge=0.0, le=5.0)
    task_completion: float = Field(ge=0.0, le=5.0)
    grounding_coherence: float = Field(ge=0.0, le=5.0)

class JudgeAnnotation(BaseModel):
    scores: JudgeScores
    failure_tags: List[str] = Field(default_factory=list)
    rationale: str = ""

class ValidationFailure(BaseModel):
    tag: str
    description: str
    step_index: Optional[int] = None

class ValidationResult(BaseModel):
    is_valid: bool
    failures: List[ValidationFailure] = Field(default_factory=list)
