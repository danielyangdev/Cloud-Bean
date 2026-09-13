"""Synchronized burstiness and inter-arrival dynamics detector."""

from datetime import datetime
import math
from typing import List

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


def _parse_ts(ts: str) -> float:
    """Parse ISO-8601 timestamp string into POSIX epoch seconds."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.timestamp()


class SynchronizedBurstDetector:
    """Detects deadline-driven coordinated pulses where agents simultaneously spike request rates."""

    def __init__(
        self,
        min_events: int = 10,
        min_actors: int = 2,
        cv_threshold: float = 1.8,
    ) -> None:
        self.min_events = min_events
        self.min_actors = min_actors
        self.cv_threshold = cv_threshold

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate event stream inter-arrival intervals for burstiness (coefficient of variation)."""
        if len(events) < self.min_events:
            return []

        actors = sorted({e.actor_id for e in events})
        if len(actors) < self.min_actors:
            return []

        # Sort chronologically
        sorted_evs = sorted(events, key=lambda e: _parse_ts(e.timestamp))
        deltas: List[float] = []

        for i in range(len(sorted_evs) - 1):
            t1 = _parse_ts(sorted_evs[i].timestamp)
            t2 = _parse_ts(sorted_evs[i + 1].timestamp)
            delta = max(0.001, t2 - t1)
            deltas.append(delta)

        if len(deltas) < 2:
            return []

        mean_delta = sum(deltas) / len(deltas)
        variance = sum((d - mean_delta) ** 2 for d in deltas) / (len(deltas) - 1)
        std_delta = math.sqrt(variance)

        # Coefficient of variation Cv = sigma / mu
        cv = std_delta / mean_delta if mean_delta > 0 else 0.0

        if cv > self.cv_threshold:
            targets = sorted({e.target for e in events if e.target})
            group_id = f"cand_burst_{window_start}_{window_end}_{len(events)}"

            return [
                CandidateGroup(
                    group_id=group_id,
                    trigger_signal="synchronized_burstiness",
                    window_start=window_start,
                    window_end=window_end,
                    target_resources=targets,
                    actors=actors,
                    event_ids=[e.event_id for e in sorted_evs],
                    metrics={
                        "coefficient_of_variation": round(cv, 3),
                        "mean_delta_seconds": round(mean_delta, 2),
                        "std_delta_seconds": round(std_delta, 2),
                        "cv_threshold": self.cv_threshold,
                        "total_events": len(sorted_evs),
                        "unique_actors": len(actors),
                    },
                    is_audit_sample=False,
                )
            ]

        return []
