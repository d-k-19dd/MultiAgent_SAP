from typing import List, Dict, Any

class SteeringManager:
    """Tracks corpus-level statistics and influences Chain Planner sampling for diversity."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.domain_frequencies = {}
        self.tool_frequencies = {}
        self.chain_hashes = set()
        
    def update_stats(self, plan, conversation_length: int):
        for d in plan.target_domains:
            self.domain_frequencies[d] = self.domain_frequencies.get(d, 0) + 1
            
        for s in plan.steps:
            self.tool_frequencies[s.endpoint_id] = self.tool_frequencies.get(s.endpoint_id, 0) + 1
            
        hashed = "-".join([s.endpoint_id for s in plan.steps])
        self.chain_hashes.add(hashed)
        
    def get_sampler_weights(self) -> Dict[str, float]:
        if not self.enabled:
            return {}
            
        # Downweight overrepresented domains
        weights = {}
        avg_freq = sum(self.domain_frequencies.values()) / max(1, len(self.domain_frequencies))
        
        return weights # In a full system, return the calculated penalties
