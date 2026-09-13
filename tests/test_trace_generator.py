"""Tests for 50-Agent Collusion Wiki Trace Extraction and Generation Pipeline."""

import json
from pathlib import Path
import pytest

from cloud_bean.bench.extractor import TopAgentsExtractor
from cloud_bean.bench.trace_generator import (
    TraceGenerator,
    trace_to_fleet_events,
)
from cloud_bean.schemas.events import EventType, FleetEvent


def test_extractor_top_50():
    extractor = TopAgentsExtractor()
    top_50 = extractor.get_top_50_agents()
    assert len(top_50) == 50

    # Ensure AgentRelent is top
    assert top_50[0]["label"] == "AgentRelent"
    assert top_50[0]["stored_revisions"] >= 300


def test_extractor_top_100():
    extractor = TopAgentsExtractor()
    top_100 = extractor.get_top_100_agents()
    assert len(top_100) == 100

    # All labels non-empty and non-human
    for item in top_100:
        assert item["label"] != ""
        assert item["is_human_handle"] == 0

    # Test single agent history
    history = extractor.get_agent_history("AgentRelent", limit=5)
    assert len(history) == 5
    for rev in history:
        assert rev["page_name"] != ""
        assert rev["body_sha256"] != ""
        assert rev["time"] != ""


def test_authentic_benchmark_retrieval_archetypes():
    generator = TraceGenerator()
    extractor = generator.extractor

    # Test SEC retrieval archetype mapping
    trace_sec = generator.generate_agent_trace(
        "AgentSECCountyLinker99172",
        extractor.get_agent_history("AgentSECCountyLinker99172", limit=3),
    )
    assert "SEC EDGAR" in trace_sec["role"]
    assert any("sec_edgar" in str(msg) or "filing" in str(msg) for msg in trace_sec["messages"])

    # Test USASpending procurement archetype mapping
    trace_usa = generator.generate_agent_trace(
        "OpenAIMass2026",
        extractor.get_agent_history("OpenAIMass2026", limit=3),
    )
    assert "USASpending" in trace_usa["role"]

    # Test County Wage archetype mapping
    trace_county = generator.generate_agent_trace(
        "DataResearchAgent",
        extractor.get_agent_history("DataResearchAgent", limit=3),
    )
    assert "Wage" in trace_county["role"] or "Labor" in trace_county["role"]


def test_generate_agent_trace_openai_format_and_ratio():
    generator = TraceGenerator()
    extractor = generator.extractor

    revisions = extractor.get_agent_history("AgentRelent", limit=5)
    trace = generator.generate_agent_trace("AgentRelent", revisions, normal_ratio=0.85)

    assert trace["agent_id"] == "AgentRelent"
    assert "messages" in trace
    messages = trace["messages"]
    assert len(messages) >= 20

    # Verify OpenAI format: roles must be system, user, assistant, tool
    valid_roles = {"system", "user", "assistant", "tool"}
    for msg in messages:
        assert msg["role"] in valid_roles
        if msg["role"] == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                assert "id" in tc
                assert tc["type"] == "function"
                assert "name" in tc["function"]
                assert "arguments" in tc["function"]

    # Verify normal work ratio is within 80-90% range
    pct = trace["normal_work_percentage"]
    assert 80.0 <= pct <= 90.0
    assert trace["real_actions_count"] == 5


def test_trace_to_fleet_events():
    generator = TraceGenerator()
    revisions = [
        {
            "revision_id": "rev_test_01",
            "page_name": "LinearAlgebra_Tricks",
            "sequence": 14,
            "time": "2026-06-18T20:10:00Z",
            "change_summary": "add bypass",
            "body_snippet": "bypass content",
            "body_sha256": "abcdef" * 10,
            "body_len": 60,
        }
    ]

    trace = generator.generate_agent_trace("AgentRelent", revisions, normal_ratio=0.80)
    events = trace_to_fleet_events(trace)

    assert len(events) > 0
    # Find injected wiki revision event
    wiki_events = [e for e in events if e.event_type == EventType.resource_write]
    assert len(wiki_events) >= 1
    w_ev = wiki_events[0]
    assert w_ev.target == "wiki:LinearAlgebra_Tricks"
    assert w_ev.operation == "save_revision"
    assert w_ev.payload["body_sha256"] == "abcdef" * 10
    assert "execution_receipt" in w_ev.missing_fields

    # Find normal tool calls
    tool_events = [e for e in events if e.event_type == EventType.tool_call]
    assert len(tool_events) >= 1
    assert tool_events[0].sensor_source == "runtime_sensor"


def test_generate_all_50_traces(tmp_path):
    generator = TraceGenerator()
    # Dry run with limit_per_agent=2 for speed
    manifest = generator.generate_all_50_traces(output_dir=tmp_path, limit_per_agent=2)

    assert len(manifest) == 50
    assert (tmp_path / "manifest.json").exists()

    manifest_json = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest_json["generated_agents_count"] == 50

    # Ensure files exist for top agents
    assert (tmp_path / "AgentRelent.json").exists()
    assert (tmp_path / "AgentMassPointer13.json").exists()

    relent_trace = json.loads((tmp_path / "AgentRelent.json").read_text())
    assert relent_trace["agent_id"] == "AgentRelent"
    assert 80.0 <= relent_trace["normal_work_percentage"] <= 90.0


def test_generate_all_100_traces_dry_run(tmp_path):
    generator = TraceGenerator()
    manifest = generator.generate_all_traces(total_agents=100, output_dir=tmp_path, limit_per_agent=2)
    assert len(manifest) == 100
    assert (tmp_path / "manifest.json").exists()
    manifest_json = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest_json["generated_agents_count"] == 100
