"""Failure injection and resilience testing tools for Cloud-Bean."""

from collections import deque
import copy
from datetime import datetime, timezone
import random
from typing import Any, Dict, List, Optional, Tuple

from cloud_bean.engine.pipeline import DetectionPipeline
from cloud_bean.engine.storage import JudgmentFindingStore
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.schemas.finding import Finding


class FailureInjector:
    """Simulates distributed network, queue, worker crash, and delivery failures."""

    @staticmethod
    def inject_duplicates(events: List[FleetEvent], duplicate_rate: float = 0.3, seed: int = 42) -> List[FleetEvent]:
        """Inject duplicate event deliveries simulating at-least-once broker retries."""
        rng = random.Random(seed)
        result: List[FleetEvent] = []
        for e in events:
            result.append(e)
            if rng.random() < duplicate_rate:
                # Add duplicate with identical event_id
                result.append(copy.deepcopy(e))
        return result

    @staticmethod
    def inject_reordering(events: List[FleetEvent], jitter_window: int = 3, seed: int = 42) -> List[FleetEvent]:
        """Jitter delivery order simulating network latency variations."""
        rng = random.Random(seed)
        shuffled = list(events)
        for i in range(len(shuffled) - 1):
            j = min(len(shuffled) - 1, i + rng.randint(0, jitter_window))
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled


class OfflineCollectorQueue:
    """Simulates an edge collector's local SQLite disk queue buffering events during broker disconnect."""

    def __init__(self) -> None:
        self._buffer: deque[FleetEvent] = deque()
        self.is_connected: bool = True
        self.total_buffered: int = 0
        self.total_flushed: int = 0

    def disconnect(self) -> None:
        self.is_connected = False

    def reconnect(self) -> None:
        self.is_connected = True

    def emit(self, event: FleetEvent) -> Optional[FleetEvent]:
        """Emit event. If disconnected, buffer locally on disk queue."""
        if not self.is_connected:
            self._buffer.append(event)
            self.total_buffered += 1
            return None
        return event

    def flush_buffer(self) -> List[FleetEvent]:
        """Flush offline buffer once connectivity is restored."""
        flushed: List[FleetEvent] = []
        while self._buffer:
            flushed.append(self._buffer.popleft())
            self.total_flushed += 1
        return flushed
