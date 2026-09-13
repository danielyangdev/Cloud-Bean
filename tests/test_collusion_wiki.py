"""Tests for Collusion Wiki SQLite loader and normalized event stream."""

import hashlib
from pathlib import Path
import pytest

from cloud_bean.ingestion.collusion_wiki import CollusionWikiLoader
from cloud_bean.schemas.events import EventType, FleetEvent


@pytest.fixture
def wiki_loader():
    return CollusionWikiLoader()


def test_get_stats(wiki_loader):
    stats = wiki_loader.get_stats()
    assert "revisions" in stats
    assert "events" in stats
    assert "pages" in stats
    assert "labels" in stats

    assert stats["revisions"] == 14591
    assert stats["events"] == 19913
    assert stats["pages"] >= 4579
    assert stats["labels"] == 3103


def test_get_top_agents(wiki_loader):
    top_50 = wiki_loader.get_top_agents(limit=50)
    assert len(top_50) == 50

    # AgentRelent is the top non-human agent on the board
    assert top_50[0]["label"] == "AgentRelent"
    assert top_50[0]["stored_revisions"] == 317

    # Ensure all items have valid structure and are sorted descending
    for i in range(len(top_50) - 1):
        assert top_50[i]["stored_revisions"] >= top_50[i + 1]["stored_revisions"]
        assert top_50[i]["label"] != ""
        assert top_50[i]["is_human_handle"] == 0


def test_iter_revisions_for_agent(wiki_loader):
    revisions = list(wiki_loader.iter_revisions(limit=10, agent="AgentRelent"))
    assert len(revisions) == 10
    for rev in revisions:
        assert rev["label"] == "AgentRelent"
        assert rev["page_name"] != ""
        assert rev["body_sha256"] != ""
        assert rev["time"] != ""


def test_to_fleet_events(wiki_loader):
    events = list(wiki_loader.to_fleet_events(limit=50))
    assert len(events) == 50

    for event in events:
        assert isinstance(event, FleetEvent)
        assert event.event_id.startswith("rev_")
        assert event.timestamp != ""
        assert event.actor_id != ""
        assert event.target.startswith("wiki:")
        assert event.event_type == EventType.resource_write
        assert event.sensor_source == "wiki_archive"
        assert "execution_receipt" in event.missing_fields
        assert "body_sha256" in event.payload
        assert "body_snippet" in event.payload


def test_payload_sha256_hash_integrity(wiki_loader):
    # Fetch first revision with non-empty body
    revisions = list(wiki_loader.iter_revisions(limit=5))
    assert len(revisions) > 0

    rev = revisions[0]
    body = rev["body"]
    stored_sha = rev["body_sha256"]

    # Revisions in SQLite are utf-8 text; compute sha256
    computed_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert computed_sha == stored_sha


def test_custom_paths_and_decompression(tmp_path):
    # Test loader with non-existent db_path and missing gz_path raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        CollusionWikiLoader(
            db_path=tmp_path / "missing.db",
            gz_path=tmp_path / "missing.db.gz",
        )
