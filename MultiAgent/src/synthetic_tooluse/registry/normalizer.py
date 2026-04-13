import json
from typing import List, Dict, Any
from synthetic_tooluse.schemas.registry import (
    ToolDefinition, EndpointDescriptor, ParameterDefinition, 
    ResponseSchema, SchemaField, ParamType, SemanticRole
)

class RegistryNormalizer:
    """Normalizes raw inconsistent ToolBench-like JSON into formal ToolDefinition objects."""
    
    def normalize_corpus(self, raw_data: List[Dict[str, Any]]) -> List[ToolDefinition]:
        tools = []
        for raw_tool in raw_data:
            tool = self._normalize_tool(raw_tool)
            if tool:
                tools.append(tool)
        return tools
        
    def _normalize_tool(self, data: Dict[str, Any]) -> ToolDefinition:
        tool_id = data.get("tool_id") or data.get("id", "unk_tool")
        endpoints = []
        
        raw_endpoints = data.get("endpoints", data.get("api_list", []))
        for raw_ep in raw_endpoints:
            endpoints.append(self._normalize_endpoint(raw_ep))
            
        return ToolDefinition(
            tool_id=tool_id,
            tool_name=data.get("tool_name", data.get("name", tool_id)),
            category=data.get("category", data.get("domain", "general")),
            domain=data.get("category", data.get("domain", "general")),
            tool_description=data.get("description", ""),
            endpoints=endpoints,
            source_metadata={"original_keys": list(data.keys())}
        )
        
    def _normalize_endpoint(self, data: Dict[str, Any]) -> EndpointDescriptor:
        ep_id = data.get("endpoint_id", data.get("name", "unk_ep"))
        
        params = []
        for raw_p in data.get("parameters", data.get("inputs", [])):
            params.append(self._normalize_parameter(raw_p))
            
        raw_resp = data.get("response") or data.get("returns")
        if raw_resp is None and isinstance(data.get("response_schema"), dict):
            raw_resp = self._response_schema_fields_to_properties(data["response_schema"])
        resp_schema = self._normalize_response(raw_resp or {})
        
        return EndpointDescriptor(
            endpoint_id=ep_id,
            endpoint_name=data.get("endpoint_name", ep_id),
            endpoint_description=data.get("description", ""),
            http_method=data.get("method", "GET").upper(),
            path=data.get("path", ""),
            input_parameters=params,
            response_schema=resp_schema,
            quality_flags=["inferred_defaults"] if not data.get("parameters") else []
        )
        
    def _normalize_parameter(self, data: Dict[str, Any]) -> ParameterDefinition:
        name = data.get("name", "unk_param")
        raw_type = str(data.get("type", "string")).lower()
        
        # Infer type
        ptype = ParamType.STRING
        if "int" in raw_type: ptype = ParamType.INTEGER
        elif "float" in raw_type or "num" in raw_type: ptype = ParamType.FLOAT
        elif "bool" in raw_type: ptype = ParamType.BOOLEAN
        elif "date" in raw_type: ptype = ParamType.DATE
        elif "array" in raw_type or "list" in raw_type: ptype = ParamType.ARRAY
        
        # Infer semantic role basic heuristic
        role = SemanticRole.UNKNOWN
        name_lower = name.lower()
        if "id" in name_lower: role = SemanticRole.IDENTIFIER
        elif "city" in name_lower or "loc" in name_lower: role = SemanticRole.LOCATION
        elif "date" in name_lower or "time" in name_lower: role = SemanticRole.DATE_RANGE
        elif "query" in name_lower or "search" in name_lower: role = SemanticRole.FREE_TEXT
        
        req = data.get("required", False)
        # handle literal string "true"
        if isinstance(req, str): req = req.lower() == "true"
        
        return ParameterDefinition(
            name=name,
            normalized_type=ptype,
            required=bool(req),
            enum_values=data.get("enum", data.get("enum_values", None)),
            description=data.get("description", ""),
            semantic_role=role
        )
        
    def _response_schema_fields_to_properties(self, response_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Map ToolBench-style response_schema.fields into OpenAPI-like properties."""
        props: Dict[str, Any] = {}
        for fld in response_schema.get("fields") or []:
            if not isinstance(fld, dict):
                continue
            name = fld.get("name", "field")
            props[name] = {"type": fld.get("type", "string")}
        return {"properties": props} if props else {}

    def _normalize_response(self, data: Dict[str, Any]) -> ResponseSchema:
        fields = []
        entity_types = set()
        
        # Just a flat heuristic parse for the scope of the exercise
        properties = data.get("properties", data) if isinstance(data, dict) else {}
        if not isinstance(properties, dict):
            properties = {}
        for k, v in properties.items():
            if isinstance(v, dict):
                kl = k.lower()
                is_id = kl.endswith("_id") or kl == "id"
                f_type = v.get("type", "string")
                ent_type = kl[:-3] if kl.endswith("_id") else (kl if is_id else None)
                if ent_type:
                    entity_types.add(ent_type)
                
                fields.append(SchemaField(
                    name=k, type=f_type, is_id_bearing=is_id, inferred_entity_type=ent_type
                ))
            else:
                kl = k.lower()
                is_id = kl.endswith("_id") or kl == "id"
                fields.append(SchemaField(name=k, type="string", is_id_bearing=is_id))
                
        return ResponseSchema(
            fields=fields,
            inferred_entity_types=list(entity_types)
        )
