import networkx as nx
from typing import Dict, List, Optional

from synthetic_tooluse.schemas.graph import ChainConstraints
from synthetic_tooluse.schemas.registry import ToolDefinition
from synthetic_tooluse.generation.chain_planner import build_chain_plan


class ChainSampler:
    """Samples realistic tool chains from the Tool Graph under constraints."""

    def __init__(self, graph: nx.DiGraph, registry: List[ToolDefinition], steering_weights: Optional[dict] = None):
        self.graph = graph
        self.registry_list = registry
        self.registry: Dict[str, ToolDefinition] = {t.tool_id: t for t in registry}
        self.endpoints = {}
        for t in registry:
            for ep in t.endpoints:
                self.endpoints[ep.endpoint_id] = ep
        self.steering_weights = steering_weights or {}

    def sample(self, constraints: ChainConstraints):
        return build_chain_plan(self.graph, self.registry, self.endpoints, constraints)
