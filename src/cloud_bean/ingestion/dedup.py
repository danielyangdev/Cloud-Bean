"""Idempotent event deduplicator for distributed cloud telemetry ingestion.

Grounding:
- End-to-End Arguments in System Design (Saltzer, Reed, Clark, 1984):
  At-least-once distributed transports require receiver-side idempotent deduplication
  to ensure exactly-once processing semantics without global consensus.
- Kafka / JetStream Idempotent Protocol: Bounded sliding-window deduplication
  prevents duplicate events from triggering redundant detector computation or
  skewing statistical inter-arrival dynamics.
"""

from collections import deque
import threading
from typing import List, Set, Tuple
from cloud_bean.schemas.events import FleetEvent


class IdempotentEventDeduplicator:
    """Thread-safe bounded sliding-window deduplicator for incoming telemetry streams."""

    def __init__(self, capacity: int = 50000) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._lock = threading.Lock()
        self._seen_ids: Set[str] = set()
        self._order: deque[str] = deque()

    @property
    def size(self) -> int:
        """Current number of tracked event IDs in the sliding window."""
        with self._lock:
            return len(self._seen_ids)

    def is_duplicate(self, event_id: str) -> bool:
        """Check whether an event ID has already been observed in the sliding window."""
        with self._lock:
            return event_id in self._seen_ids

    def filter_events(self, events: List[FleetEvent]) -> Tuple[List[FleetEvent], int]:
        """Filter out duplicate events from an incoming batch.

        Returns:
            Tuple[List[FleetEvent], int]: (unique_events, suppressed_count)
        """
        if not events:
            return [], 0

        unique_events: List[FleetEvent] = []
        suppressed_count = 0

        with self._lock:
            for ev in events:
                eid = ev.event_id
                if eid in self._seen_ids:
                    suppressed_count += 1
                    continue

                self._seen_ids.add(eid)
                self._order.append(eid)
                unique_events.append(ev)

                if len(self._order) > self.capacity:
                    evicted = self._order.popleft()
                    self._seen_ids.discard(evicted)

        return unique_events, suppressed_count

    def clear(self) -> None:
        """Clear all tracked event IDs."""
        with self._lock:
            self._seen_ids.clear()
            self._order.clear()
