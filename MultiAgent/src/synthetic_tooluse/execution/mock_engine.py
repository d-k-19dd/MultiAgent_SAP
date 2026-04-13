import random
import string
from typing import Dict, Any, List

from synthetic_tooluse.schemas.registry import EndpointDescriptor, SchemaField
from synthetic_tooluse.execution.state import SessionState


class MockExecutionEngine:
    """Executes tool calls offline by generating schema-conformant mock data."""

    def __init__(self, endpoints: List[EndpointDescriptor]):
        self.endpoints = {ep.endpoint_id: ep for ep in endpoints}

    def execute(self, endpoint_id: str, arguments: Dict[str, Any], session: SessionState) -> Dict[str, Any]:
        ep = self.endpoints.get(endpoint_id)
        if not ep:
            return {"error": f"Endpoint {endpoint_id} not globally recognized."}

        response: Dict[str, Any] = {}
        if ep.response_schema.fields:
            for field in ep.response_schema.fields:
                response[field.name] = self._generate_mock_value(field, session, arguments)
        else:
            ep_string = endpoint_id.lower()
            domain = ep_string.split("/")[0] if "/" in ep_string else "generic"
            if "search" in ep_string or "list" in ep_string or "get" in ep_string:
                list_id = session.entity_store.create_entity(domain, dict(arguments))
                response["results"] = [
                    {
                        "id": list_id,
                        "name": f"Mock {domain.capitalize()} Result",
                        "status": "available",
                    }
                ]
            elif "book" in ep_string or "buy" in ep_string or "pay" in ep_string or "transaction" in ep_string:
                conf_id = session.entity_store.create_entity(f"{domain}_confirmation", dict(arguments))
                response["confirmation_id"] = conf_id
                response["status"] = "success"
                response["amount"] = random.randint(50, 500)
            else:
                gen_id = session.entity_store.create_entity(f"{domain}_entity", dict(arguments))
                response["id"] = gen_id
                response["details"] = "Action completed requested bounds."

        session.record_tool_output(response)
        return response

    def _generate_mock_value(self, field: SchemaField, session: SessionState, arguments: Dict[str, Any]) -> Any:
        fname = field.name.lower()

        # IDs must be created via EntityStore so validators can ground references.
        if field.is_id_bearing or fname.endswith("_id") or fname == "id":
            ent_type = field.inferred_entity_type or fname.replace("_id", "").strip("_") or "entity"
            return session.entity_store.create_entity(ent_type, {"field": field.name, "args": dict(arguments)})

        if field.type == "string":
            if "status" in fname:
                return random.choice(["success", "confirmed", "processed"])
            if "summary" in fname:
                return f"Summary for {arguments.get('query') or arguments.get('article_id') or 'request'}."
            return f"mock_{field.name}_{''.join(random.choices(string.ascii_lowercase, k=4))}"
        if field.type == "integer":
            if "price" in fname or "rate" in fname or "usd" in fname or "income" in fname:
                return random.randint(200, 900)
            if "count" in fname:
                return random.randint(1, 5)
            return random.randint(1, 100)
        if field.type == "boolean":
            return True
        if field.type == "array":
            return [f"item_{random.randint(1, 10)}", f"item_{random.randint(11, 20)}"]

        return f"mock_{field.name}"
