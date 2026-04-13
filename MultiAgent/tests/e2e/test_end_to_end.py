import pytest
import os
import json
from typer.testing import CliRunner

runner = CliRunner()


def test_end_to_end_pipeline(tmp_path, monkeypatch):
    # Force deterministic offline agents even if developer API keys are present in the environment.
    monkeypatch.setattr("synthetic_tooluse.config.USE_MOCK_LLM", True)
    monkeypatch.setattr("synthetic_tooluse.agents.base.USE_MOCK_LLM", True)
    monkeypatch.setattr("synthetic_tooluse.agents.judge.USE_MOCK_LLM", True)
    monkeypatch.setattr("synthetic_tooluse.agents.assistant_orchestrator.USE_MOCK_LLM", True)

    from synthetic_tooluse.cli import app

    artifact_dir = tmp_path / "artifacts"
    data_dir = tmp_path / "data"
    raw_path = data_dir / "raw_tools.json"
    
    # Run Build
    result = runner.invoke(app, ["build", "--input", str(raw_path), "--artifact-dir", str(artifact_dir)])
    assert result.exit_code == 0
    assert os.path.exists(artifact_dir / "registry.json")
    
    # Run Generate
    output_a = data_dir / "run_a.jsonl"
    result = runner.invoke(app, ["generate", "--artifact-dir", str(artifact_dir), "--num-samples", "10", "--output", str(output_a)])
    assert result.exit_code == 0
    assert os.path.exists(output_a)
    
    # Validation constraint check > check lines exist
    with open(output_a, "r") as f:
        lines = f.readlines()
        assert len(lines) == 10
        
    # Evaluate
    report_a = data_dir / "eval_a.json"
    result = runner.invoke(app, ["evaluate", "--input", str(output_a), "--report", str(report_a)])
    assert result.exit_code == 0
    
    with open(report_a, "r") as f:
        metrics = json.load(f)
        assert metrics["mean_task_completion"] >= 1.0 # Should be 4.0 fallback mock
