from typing import Dict, Any, List
import uuid

class EntityStore:
    """Maintains referential integrity by generating stable synthetic IDs and tracking entities."""
    def __init__(self):
        self.entities: Dict[str, Dict[str, Any]] = {}  # type -> {id -> record}
        self.id_to_type: Dict[str, str] = {}
        
    def create_entity(self, entity_type: str, record: Dict[str, Any]) -> str:
        new_id = f"{entity_type[:3]}_{uuid.uuid4().hex[:6]}"
        record["id"] = new_id
        if entity_type not in self.entities:
            self.entities[entity_type] = {}
        self.entities[entity_type][new_id] = record
        self.id_to_type[new_id] = entity_type
        return new_id

class SessionState:
    """Maintains state for a single conversation trace."""
    def __init__(self):
        self.entity_store = EntityStore()
        self.extracted_slots: Dict[str, Any] = {}
        self.recent_tool_outputs: List[Dict[str, Any]] = []
        
    def record_tool_output(self, output: Dict[str, Any]):
        self.recent_tool_outputs.append(output)
        
    def update_slots(self, slots: Dict[str, Any]):
        self.extracted_slots.update(slots)
