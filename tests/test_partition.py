"""Tests for distributed consistent hash router and shard partitioning."""

from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest

from cloud_bean.api.app import create_app
from cloud_bean.engine.partition import ConsistentHashRouter
from cloud_bean.schemas.events import EventType, FleetEvent


def test_router_initialization_and_validation():
    with pytest.raises(ValueError, match="vnodes must be at least 1"):
        ConsistentHashRouter(vnodes=0)

    router = ConsistentHashRouter()
    assert router.shards == []

    with pytest.raises(ValueError, match="shard_id cannot be empty"):
        router.add_shard("")

    with pytest.raises(RuntimeError, match="no shards registered"):
        router.get_shard("test_key")


def test_deterministic_routing():
    shards = ["shard_0", "shard_1", "shard_2", "shard_3"]
    router = ConsistentHashRouter(shard_ids=shards, vnodes=64)

    # Determinism: same key returns exact same shard across multiple calls
    for key in ["agent_001", "agent_042", "wiki/bypass", "task_retrieval"]:
        s1 = router.get_shard(key)
        s2 = router.get_shard(key)
        assert s1 == s2
        assert s1 in shards


def test_distribution_uniformity():
    shards = ["worker-a", "worker-b", "worker-c", "worker-d"]
    router = ConsistentHashRouter(shard_ids=shards, vnodes=128)

    keys = [f"agent_{i:03d}" for i in range(200)]
    stats = router.get_distribution_stats(keys)

    assert set(stats.keys()) == set(shards)
    assert sum(stats.values()) == 200

    # Each shard should receive a reasonable fraction (no shard starved)
    for shard, count in stats.items():
        assert count > 20, f"Shard {shard} received unexpectedly few keys: {count}"


def test_minimal_keyspace_remapping():
    """Dynamo property: adding a shard only moves keys to the new shard, not between existing shards."""
    initial_shards = ["shard_0", "shard_1", "shard_2"]
    router = ConsistentHashRouter(shard_ids=initial_shards, vnodes=128)

    keys = [f"key_{i:04d}" for i in range(100)]
    initial_mapping = {k: router.get_shard(k) for k in keys}

    # Add 4th shard
    router.add_shard("shard_3")
    new_mapping = {k: router.get_shard(k) for k in keys}

    for k in keys:
        old_shard = initial_mapping[k]
        new_shard = new_mapping[k]
        if old_shard != new_shard:
            # Key must have moved to the newly added shard, not to another old shard
            assert new_shard == "shard_3"


def test_shard_removal():
    shards = ["node-1", "node-2", "node-3"]
    router = ConsistentHashRouter(shard_ids=shards, vnodes=64)

    keys = [f"agent_{i}" for i in range(50)]
    router.remove_shard("node-2")
    assert router.shards == ["node-1", "node-3"]

    for k in keys:
        shard = router.get_shard(k)
        assert shard in ["node-1", "node-3"]

    # Removing non-existent shard is a no-op
    router.remove_shard("node-999")
    assert router.shards == ["node-1", "node-3"]


def test_route_and_partition_events():
    shards = ["shard_0", "shard_1"]
    router = ConsistentHashRouter(shard_ids=shards, vnodes=32)

    now_iso = datetime.now(timezone.utc).isoformat()
    events = [
        FleetEvent(
            event_id=f"ev_{i}",
            timestamp=now_iso,
            actor_id=f"agent_{i % 5}",
            task_id=f"task_{i % 2}",
            event_type=EventType.tool_call,
            target=f"res_{i % 3}",
        )
        for i in range(10)
    ]

    partitioned = router.partition_events(events, partition_by="actor_id")
    assert set(partitioned.keys()) == set(shards)
    total_partitioned = sum(len(ev_list) for ev_list in partitioned.values())
    assert total_partitioned == 10

    # Target-based partition
    partitioned_target = router.partition_events(events, partition_by="target")
    assert sum(len(ev_list) for ev_list in partitioned_target.values()) == 10


def test_api_shards_endpoint():
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/v1/shards?num_shards=4")
    assert res.status_code == 200
    data = res.json()
    assert data["num_shards"] == 4
    assert len(data["shards"]) == 4
    assert "distribution" in data
