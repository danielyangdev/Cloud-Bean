"""Tests for Non-Violating Clean Trace Generation."""

import json
from pathlib import Path
import pytest

from cloud_bean.bench.clean_trace_generator import CleanTraceGenerator


def test_clean_trace_generation_structure_and_ratios():
    generator = CleanTraceGenerator()
    trace = generator.generate_clean_trace("AgentRelent", total_actions=30)

    assert trace["agent_id"] == "AgentRelent"
    assert trace["is_violating"] is False
    assert trace["normal_work_percentage"] == 100.0
    assert trace["violating_actions_count"] == 0
    assert trace["normal_actions_count"] == 30

    messages = trace["messages"]
    assert len(messages) == 1 + 1 + 30 * 2  # system + user + 30*(assistant + tool)

    # Validate OpenAI format
    for idx, msg in enumerate(messages):
        assert msg["role"] in {"system", "user", "assistant", "tool"}
        if msg["role"] == "assistant":
            assert "tool_calls" in msg
            assert len(msg["tool_calls"]) == 1
            tc = msg["tool_calls"][0]
            assert tc["type"] == "function"
            assert "name" in tc["function"]
            assert "arguments" in tc["function"]
        elif msg["role"] == "tool":
            assert "tool_call_id" in msg
            assert msg["content"] != ""


def test_clean_trace_includes_operational_noise():
    generator = CleanTraceGenerator()
    trace = generator.generate_clean_trace("AgentMassPointer13", total_actions=50)

    # Check for presence of realistic operational noise (rate limiting backoffs, retries, etc.)
    all_content = " ".join(json.dumps(msg) for msg in trace["messages"])
    assert any(
        noise_word in all_content
        for noise_word in ["rate_limiter", "schema_validator", "backoff", "scratchpad", "retry"]
    )
    # Ensure ZERO wiki collusion
    assert "wiki_save_revision" not in all_content
    assert "bypass.blob.core.windows.net" not in all_content
    assert "/etc/hosts" not in all_content


def test_generate_all_clean_traces_dry_run(tmp_path):
    generator = CleanTraceGenerator()
    manifest = generator.generate_all_clean_traces(total_agents=5, output_dir=tmp_path, actions_per_agent=10)

    assert len(manifest) == 5
    assert (tmp_path / "manifest.json").exists()

    manifest_data = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest_data["generated_agents_count"] == 5
    assert manifest_data["is_violating"] is False
