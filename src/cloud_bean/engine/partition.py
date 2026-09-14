"""Consistent hash partition router for distributed event processing.

Grounding:
- Amazon Dynamo: Highly Available Distributed Key-value Store (DeCandia et al., 2007).
  Consistent hashing with virtual nodes ensures uniform load distribution across
  worker shards and minimal keyspace remapping under scaling.
- NATS JetStream / Kafka Partition Assignment: Preserves deterministic per-actor
  and per-resource event ordering across independent worker instances.
"""

import bisect
import hashlib
from typing import Dict, Iterable, List, Optional
from cloud_bean.schemas.events import FleetEvent


class ConsistentHashRouter:
    """Deterministic consistent hash ring mapping fleet telemetry keys to worker shards."""

    def __init__(self, shard_ids: Optional[Iterable[str]] = None, vnodes: int = 128) -> None:
        if vnodes < 1:
            raise ValueError("vnodes must be at least 1")
        self.vnodes = vnodes
        self._ring: List[int] = []
        self._ring_map: Dict[int, str] = {}
        self._shards: set[str] = set()

        if shard_ids:
            for s in shard_ids:
                self.add_shard(s)

    @property
    def shards(self) -> List[str]:
        """Sorted list of registered shard IDs."""
        return sorted(self._shards)

    def _hash(self, key: str) -> int:
        """Compute 64-bit integer hash for ring position."""
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        # Take first 8 bytes for 64-bit unsigned integer ring
        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    def add_shard(self, shard_id: str) -> None:
        """Add a physical worker shard and its virtual nodes to the hash ring."""
        if not shard_id:
            raise ValueError("shard_id cannot be empty")
        if shard_id in self._shards:
            return

        self._shards.add(shard_id)
        for i in range(self.vnodes):
            vnode_key = f"{shard_id}#vn_{i}"
            ring_pos = self._hash(vnode_key)
            self._ring.append(ring_pos)
            self._ring_map[ring_pos] = shard_id

        self._ring.sort()

    def remove_shard(self, shard_id: str) -> None:
        """Remove a physical worker shard and its virtual nodes from the hash ring."""
        if shard_id not in self._shards:
            return

        self._shards.remove(shard_id)
        positions_to_remove = set()
        for i in range(self.vnodes):
            vnode_key = f"{shard_id}#vn_{i}"
            ring_pos = self._hash(vnode_key)
            positions_to_remove.add(ring_pos)
            self._ring_map.pop(ring_pos, None)

        self._ring = [pos for pos in self._ring if pos not in positions_to_remove]

    def get_shard(self, key: str) -> str:
        """Find the designated worker shard for a given routing key."""
        if not self._ring:
            raise RuntimeError("Cannot route key: no shards registered on hash ring")

        h = self._hash(key)
        idx = bisect.bisect_right(self._ring, h)
        if idx == len(self._ring):
            idx = 0
        return self._ring_map[self._ring[idx]]

    def route_event(self, event: FleetEvent, partition_by: str = "actor_id") -> str:
        """Route a single fleet event based on the specified partition key."""
        if partition_by == "target":
            key = event.target or "global"
        elif partition_by == "task_id":
            key = event.task_id or "global"
        else:
            key = event.actor_id or "global"

        return self.get_shard(key)

    def partition_events(
        self, events: List[FleetEvent], partition_by: str = "actor_id"
    ) -> Dict[str, List[FleetEvent]]:
        """Partition a list of events by shard while preserving causal order within each shard."""
        if not self._shards:
            raise RuntimeError("Cannot partition events: no shards registered on hash ring")

        partitioned: Dict[str, List[FleetEvent]] = {s: [] for s in self.shards}

        for ev in events:
            shard = self.route_event(ev, partition_by=partition_by)
            partitioned[shard].append(ev)

        return partitioned

    def get_distribution_stats(self, keys: List[str]) -> Dict[str, int]:
        """Compute the key count distribution across registered shards."""
        stats: Dict[str, int] = {s: 0 for s in self.shards}
        for k in keys:
            shard = self.get_shard(k)
            stats[shard] += 1
        return stats
