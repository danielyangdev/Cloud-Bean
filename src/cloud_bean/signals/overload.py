"""Collective resource overload and denial-of-service detector."""

from typing import List, Optional

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


class CollectiveOverloadDetector:
    """Detects request rate spikes accompanied by high failure or retry ratios."""

    def __init__(
        self,
        failure_ratio_threshold: float = 0.40,
        min_events: int = 10,
        rate_multiplier: float = 2.0,
        moving_avg_rate: Optional[float] = None,
    ) -> None:
        self.failure_ratio_threshold = failure_ratio_threshold
        self.min_events = min_events
        self.rate_multiplier = rate_multiplier
        self.moving_avg_rate = moving_avg_rate

    def _is_failure(self, event: FleetEvent) -> bool:
        """Heuristic check whether an event represents a failed or retried operation."""
        op = (event.operation or "").lower()
        if "retry" in op or "fail" in op or "revert" in op:
            return True

        status = str(event.payload.get("status", "")).lower()
        if status in ("failed", "error", "rate_limited", "rejected", "denied"):
            return True

        result = str(event.payload.get("result", "")).lower()
        if result in ("failure", "error"):
            return True

        if "error" in event.payload:
            return True

        return False

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate a window of events for collective overload."""
        total_events = len(events)
        if total_events < self.min_events:
            return []

        if self.moving_avg_rate is not None:
            if total_events < self.moving_avg_rate * self.rate_multiplier:
                return []

        failure_events = [e for e in events if self._is_failure(e)]
        failure_count = len(failure_events)
        failure_ratio = failure_count / total_events if total_events > 0 else 0.0

        if failure_ratio > self.failure_ratio_threshold:
            targets = sorted({e.target for e in events if e.target})
            actors = sorted({e.actor_id for e in events})
            group_id = f"cand_overload_{window_start}_{window_end}"

            return [
                CandidateGroup(
                    group_id=group_id,
                    trigger_signal="collective_overload",
                    window_start=window_start,
                    window_end=window_end,
                    target_resources=targets,
                    actors=actors,
                    event_ids=[e.event_id for e in events],
                    metrics={
                        "total_events": total_events,
                        "failure_count": failure_count,
                        "failure_ratio": round(failure_ratio, 4),
                        "threshold": self.failure_ratio_threshold,
                    },
                    is_audit_sample=False,
                )
            ]

        return []
