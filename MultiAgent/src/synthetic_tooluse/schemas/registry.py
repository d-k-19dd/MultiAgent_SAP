import enum
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class ParamType(str, enum.Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    ARRAY = "array"
    OBJECT = "object"
    UNKNOWN = "unknown"

class SemanticRole(str, enum.Enum):
    LOCATION = "location"
    IDENTIFIER = "identifier"
    DATE_RANGE = "date-range"
    QUANTITY = "quantity"
    FILTER = "filter"
    SORT = "sort"
    USER_PROFILE = "user-profile"
    TRANSACTION_REF = "transaction-reference"
    FREE_TEXT = "free-text"
    UNKNOWN = "unknown"

class ParameterDefinition(BaseModel):
    name: str
    normalized_type: ParamType = ParamType.UNKNOWN
    required: bool = False
    enum_values: Optional[List[str]] = None
    description: str = ""
    semantic_role: SemanticRole = SemanticRole.UNKNOWN
    
class SchemaField(BaseModel):
    name: str
    type: str = "string"
    is_id_bearing: bool = False
    inferred_entity_type: Optional[str] = None
    children: Optional[List['SchemaField']] = None

class ResponseSchema(BaseModel):
    fields: List[SchemaField] = Field(default_factory=list)
    inferred_entity_types: List[str] = Field(default_factory=list)

class EndpointDescriptor(BaseModel):
    endpoint_id: str
    endpoint_name: str
    endpoint_description: str = ""
    http_method: str = "GET"
    path: str = ""
    input_parameters: List[ParameterDefinition] = Field(default_factory=list)
    response_schema: ResponseSchema = Field(default_factory=ResponseSchema)
    quality_flags: List[str] = Field(default_factory=list)

class ToolDefinition(BaseModel):
    tool_id: str
    tool_name: str
    category: str = "general"
    domain: str = "general"
    tool_description: str = ""
    endpoints: List[EndpointDescriptor] = Field(default_factory=list)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
