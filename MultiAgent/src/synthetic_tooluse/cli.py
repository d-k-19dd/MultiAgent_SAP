import json
import logging
from pydantic import BaseModel
import typer
import random
import os
from pathlib import Path

from synthetic_tooluse.registry.normalizer import RegistryNormalizer
from synthetic_tooluse.graph.builder import GraphBuilder
from synthetic_tooluse.schemas.graph import ChainConstraints
from synthetic_tooluse.generation.pipeline import GenerationPipeline
from synthetic_tooluse.evaluation.metrics import compute_corpus_metrics
from synthetic_tooluse.evaluation.trace_analyzer import aggregate_corpus_signals

app = typer.Typer(help="Synthetic Tool-Use Data Pipeline")

def write_jsonl(path: str, data: list):
    with open(path, 'w') as f:
        for item in data:
            f.write(item.model_dump_json() + '\n')

@app.command()
def build(input: str = typer.Option(..., help="Path to raw_tools.json"),
          artifact_dir: str = typer.Option("artifacts", help="Path to output artifacts")):
    
    os.makedirs(artifact_dir, exist_ok=True)
    input_dir = os.path.dirname(os.path.abspath(input))
    if input_dir:
        os.makedirs(input_dir, exist_ok=True)

    print(f"Building registry from {input}...")
    try:
        with open(input, 'r') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"File not found: {input}. Generating mock fixture.")
        raw_data = [
            {
                "tool_id": "hotels",
                "endpoints": [
                    {
                        "endpoint_id": "hotels/search",
                        "response": {"properties": {"hotel_id": {"type": "string"}}},
                        "parameters": [{"name": "city", "required": True}]
                    },
                    {
                        "endpoint_id": "hotels/book",
                        "response": {"properties": {"booking_id": {"type": "string"}}},
                        "parameters": [{"name": "hotel_id", "required": True}, {"name": "date", "required": True}]
                    }
                ]
            }
        ]
        with open(input, 'w') as f:
            json.dump(raw_data, f)
            
    # Normalize
    normalizer = RegistryNormalizer()
    registry = normalizer.normalize_corpus(raw_data)
    
    # Save registry
    with open(os.path.join(artifact_dir, "registry.json"), "w") as f:
        json.dump([r.model_dump() for r in registry], f, indent=2)
        
    print(f"Registry normalized: {len(registry)} tools.")
    
    # Build Graph
    builder = GraphBuilder(registry)
    graph = builder.build()
    
    print(f"Graph built: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
    
@app.command()
def generate(artifact_dir: str = typer.Option("artifacts", help="Path providing registry.json"),
             num_samples: int = typer.Option(10, help="Number of traces to generate"),
             seed: int = typer.Option(42, help="Random seed for deterministic generation"),
             output: str = typer.Option("data/generated.jsonl", help="Output filepath"),
             cross_conversation_steering: bool = typer.Option(True, "--cross-conversation-steering/--no-cross-conversation-steering", help="Toggle diversity steering"),
             max_retries: int = typer.Option(3, help="Max repair retries for missing pacing limits")):

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    output_dir = os.path.dirname(output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    random.seed(seed)
    
    reg_path = os.path.join(artifact_dir, "registry.json")
    if not os.path.exists(reg_path):
        print("Registry not found. Run `build` first.")
        return
        
    with open(reg_path, 'r') as f:
        reg_data = json.load(f)
        
    from synthetic_tooluse.schemas.registry import ToolDefinition
    registry = [ToolDefinition.model_validate(r) for r in reg_data]
    
    builder = GraphBuilder(registry)
    graph = builder.build()
    
    pipeline = GenerationPipeline(registry, graph, steering_enabled=cross_conversation_steering)
    constraints = ChainConstraints(min_num_distinct_tools=2)
    
    print(f"Generating {num_samples} records. Steering: {cross_conversation_steering}")
    records = pipeline.run_generation(count=num_samples, constraints=constraints, max_retries=max_retries)
    
    write_jsonl(output, records)
    print(f"Generation complete. Saved to {output}")

@app.command()
def evaluate(input: str = typer.Option(..., help="Path to jsonl to evaluate"),
             report: str = typer.Option(..., help="Output report json path")):
    
    import math
    from synthetic_tooluse.schemas.conversation import ConversationRecord
    
    print(f"Evaluating {input}...")
    records = []
    with open(input, 'r') as f:
        for line in f:
            records.append(ConversationRecord.model_validate_json(line))
            
    metadata_list = [r.metadata for r in records]
    
    metrics = compute_corpus_metrics(metadata_list)
    
    # Score Aggregation
    mean_nat = sum(r.judge_scores.get("naturalness", 0) for r in records) / max(1, len(records))
    mean_tc = sum(r.judge_scores.get("tool_correctness", 0) for r in records) / max(1, len(records))
    mean_task = sum(r.judge_scores.get("task_completion", 0) for r in records) / max(1, len(records))
    mean_grnd = sum(r.judge_scores.get("grounding_coherence", 0) for r in records) / max(1, len(records))

    strong_multi = [
        r
        for r in records
        if r.metadata.get("actual_num_calls", 0) >= 3 and r.metadata.get("actual_num_distinct", 0) >= 2
    ]
    metrics.update({
        "mean_naturalness": mean_nat,
        "mean_tool_correctness": mean_tc,
        "mean_task_completion": mean_task,
        "mean_grounding_coherence": mean_grnd,
        "num_records": len(records),
        "multi_tool_ratio": len(strong_multi) / max(1, len(records)),
        "distinct_tools_ge2_ratio": len([r for r in records if r.metadata.get("actual_num_distinct", 0) >= 2]) / max(1, len(records)),
    })
    metrics.update(aggregate_corpus_signals(records))
    
    report_dir = os.path.dirname(report)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
    with open(report, "w") as f:
         json.dump(metrics, f, indent=2)
         
    print(f"Report complete. Diversity & Quality metrics exported to {report}")

if __name__ == "__main__":
    app()
