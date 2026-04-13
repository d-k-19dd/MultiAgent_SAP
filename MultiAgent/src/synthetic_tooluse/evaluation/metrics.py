import json
from typing import List, Dict, Any, Tuple
import math
from collections import Counter

def calculate_entropy(frequencies: Dict[str, int]) -> float:
    total = sum(frequencies.values())
    if total == 0:
        return 0.0
        
    entropy = 0.0
    for count in frequencies.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log(p, 2)
            
    return entropy

def chain_diversity_ratio(chain_hashes: List[str]) -> float:
    if not chain_hashes:
        return 0.0
    return len(set(chain_hashes)) / len(chain_hashes)

def compute_corpus_metrics(metadata_list: List[Dict[str, Any]]) -> Dict[str, float]:
    eps = []
    chains = []
    
    for m in metadata_list:
        eps.extend(m.get("endpoints_used", []))
        ch_hash = "-".join(m.get("endpoints_used", []))
        if ch_hash:
            chains.append(ch_hash)
            
    ep_freq = Counter(eps)
    
    return {
        "endpoint_entropy": calculate_entropy(ep_freq),
        "unique_chain_ratio": chain_diversity_ratio(chains)
    }
