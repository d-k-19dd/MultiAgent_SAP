import pytest
import networkx as nx
from synthetic_tooluse.registry.normalizer import RegistryNormalizer
from synthetic_tooluse.graph.builder import GraphBuilder
from synthetic_tooluse.schemas.graph import RelationType

def test_registry_normalizer():
    raw_data = [{
        "tool_id": "test_domain",
        "endpoints": [
            {
                "endpoint_id": "ep1",
                "parameters": [{"name": "req_id", "required": "True"}],
                "response": {"properties": {"user_id": {"type": "string"}}}
            }
        ]
    }]
    
    normalizer = RegistryNormalizer()
    registry = normalizer.normalize_corpus(raw_data)
    assert len(registry) == 1
    assert registry[0].endpoints[0].input_parameters[0].required is True
    assert "user" in registry[0].endpoints[0].response_schema.inferred_entity_types

def test_graph_builder():
    raw_data = [
        {
            "tool_id": "t1",
            "endpoints": [
                {"endpoint_id": "ep1", "response": {"properties": {"my_id": {"type": "string"}}}},
                {"endpoint_id": "ep2", "parameters": [{"name": "my_id", "required": True}]}
            ]
        }
    ]
    reg = RegistryNormalizer().normalize_corpus(raw_data)
    builder = GraphBuilder(reg)
    g = builder.build()
    
    assert "ep1" in g.nodes
    assert "ep2" in g.nodes
    assert g.has_edge("ep1", "ep2") # DATA FLOW inference
