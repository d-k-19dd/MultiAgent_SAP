import networkx as nx
from typing import List, Dict, Any
from synthetic_tooluse.schemas.registry import ToolDefinition
from synthetic_tooluse.schemas.graph import RelationType, GraphEdgeProperty, GraphNodeProperty

class GraphBuilder:
    """Builds a Tool Graph capturing endpoints and relationships."""
    
    def __init__(self, registry: List[ToolDefinition]):
        self.registry = registry
        self.graph = nx.DiGraph()
        
    def build(self) -> nx.DiGraph:
        self._add_nodes()
        self._add_edges()
        return self.graph
        
    def _add_nodes(self):
        for tool in self.registry:
            for ep in tool.endpoints:
                expected_inputs = [p.name for p in ep.input_parameters if p.required]
                produced_entities = ep.response_schema.inferred_entity_types
                
                node_prop = GraphNodeProperty(
                    endpoint_id=ep.endpoint_id,
                    tool_id=tool.tool_id,
                    domain=tool.domain,
                    description=ep.endpoint_description,
                    expected_inputs=expected_inputs,
                    produced_entities=produced_entities
                )
                self.graph.add_node(ep.endpoint_id, **node_prop.model_dump())
                
    def _add_edges(self):
        nodes = list(self.graph.nodes(data=True))
        for i, (n1_id, n1_data) in enumerate(nodes):
            for j, (n2_id, n2_data) in enumerate(nodes):
                if n1_id == n2_id: continue
                
                # SAME_TOOL
                if n1_data["tool_id"] == n2_data["tool_id"]:
                    self._add_edge(n1_id, n2_id, RelationType.SAME_TOOL, weight=0.1)
                
                # SAME_DOMAIN
                elif n1_data["domain"] == n2_data["domain"]:
                    self._add_edge(n1_id, n2_id, RelationType.SAME_DOMAIN, weight=0.5)
                    
                # OUTPUT_TO_INPUT_COMPATIBLE (Data flow)
                # If n1 produces entities that n2 needs
                produced = n1_data.get("produced_entities", [])
                needed = n2_data.get("expected_inputs", [])
                
                # Heuristic matching: if needed input contains produced entity string
                for p in produced:
                    if not p: continue
                    for req in needed:
                        if p in req.lower() or "id" in req.lower():
                            self._add_edge(n1_id, n2_id, RelationType.OUTPUT_TO_INPUT_COMPATIBLE, weight=2.0)
                            break
                            
    def _add_edge(self, u: str, v: str, rel: RelationType, weight: float):
        if not self.graph.has_edge(u, v):
            self.graph.add_edge(u, v, properties=[GraphEdgeProperty(relation_type=rel, weight=weight).model_dump()])
        else:
            self.graph[u][v]["properties"].append(GraphEdgeProperty(relation_type=rel, weight=weight).model_dump())
