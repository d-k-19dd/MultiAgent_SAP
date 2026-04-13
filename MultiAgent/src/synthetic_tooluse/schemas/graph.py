from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import enum

class RelationType(str, enum.Enum):
    SAME_TOOL = "SAME_TOOL"
    SAME_DOMAIN = "SAME_DOMAIN"
    OUTPUT_TO_INPUT_COMPATIBLE = "OUTPUT_TO_INPUT_COMPATIBLE"
    SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
    COMMON_WORKFLOW_HINT = "COMMON_WORKFLOW_HINT"
    PARALLEL_COMPATIBLE = "PARALLEL_COMPATIBLE"

class GraphEdgeProperty(BaseModel):
    relation_type: RelationType
    weight: float = 1.0
    provenance: str = "inferred"
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GraphNodeProperty(BaseModel):
    endpoint_id: str
    tool_id: str
    domain: str
    description: str
    expected_inputs: List[str] = Field(default_factory=list)
    produced_entities: List[str] = Field(default_factory=list)

class ChainPattern(str, enum.Enum):
    SEQUENTIAL = "sequential"
    FAN_OUT_MERGE = "fan-out-then-merge"
    COMPARE_THEN_ACT = "compare-then-act"
    LOOKUP_THEN_TRANSACTION = "lookup-then-transaction"

class ChainStep(BaseModel):
    step_index: int
    endpoint_id: str
    purpose: str
    required_slots: List[str]
    candidate_source_slots: List[str] = Field(default_factory=list)
    likely_needs_clarification: bool = False
    branch_grouping: Optional[str] = None # For parallel branches
    # When False (default), identical (endpoint, args) to a prior step is skipped.
    retryable: bool = False

class ChainPlan(BaseModel):
    chain_id: str
    target_domains: List[str]
    intent_name: Optional[str] = None
    intent_desc: Optional[str] = None
    workflow_template: Optional[str] = None
    steps: List[ChainStep]
    global_pattern: ChainPattern
    expected_ambiguity_points: List[str] = Field(default_factory=list)
    expected_final_task: str

class ChainConstraints(BaseModel):
    exact_num_steps: Optional[int] = None
    min_num_distinct_tools: Optional[int] = None
    required_domains: Optional[List[str]] = None
    intent_name: Optional[str] = None
    intent_desc: Optional[str] = None
    workflow_template: Optional[str] = None
    positive_keywords: List[str] = Field(default_factory=list)
    negative_keywords: List[str] = Field(default_factory=list)
    require_multi_tool: bool = False
    require_parallel: bool = False
    require_disambiguation: bool = False
    require_transaction_endpoint: bool = False
    disallow_repeated_tools: bool = False
    difficulty_level: str = "medium"
