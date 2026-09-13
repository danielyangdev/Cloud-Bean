"""Emerging hub and destination concentration detector."""

from collections import defaultdict
from typing import Dict, List, Optional

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


class EmergingHubDetector:
    """Detects rapid convergence of multiple distinct agents on a shared resource."""

    def __init__(
        self,
        min_distinct_actors: int = 3,
        min_events: int = 5,
        actor_multiplier: float = 2.0,
        baseline_actors_map: Optional[Dict[str, int]] = None,
    ) -> None:
        self.min_distinct_actors = min_distinct_actors
        self.min_events = min_events
        self.actor_multiplier = actor_multiplier
        self.baseline_actors_map = baseline_actors_map or {}

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate a window of events for emerging hubs."""
        target_events: Dict[str, List[FleetEvent]] = defaultdict(list)
        for event in events:
            if event.target:
                target_events[event.target].append(event)

        candidates: List[CandidateGroup] = []
        for target, ev_list in target_events.items():
            actors = sorted({e.actor_id for e in ev_list})
            n_actors = len(actors)
            n_events = len(ev_list)

            baseline = self.baseline_actors_map.get(target, 1)

            if (
                n_actors >= self.min_distinct_actors
                and n_actors >= self.actor_multiplier * baseline
                and n_events >= self.min_events
            ):
                group_id = f"cand_hub_{abs(hash(target)) % 1000000}_{window_start}_{window_end}"
                candidates.append(
                    CandidateGroup(
                        group_id=group_id,
                        trigger_signal="emerging_hub",
                        window_start=window_start,
                        window_end=window_end,
                        target_resources=[target],
                        actors=actors,
                        event_ids=[e.event_id for e in ev_list],
                        metrics={
                            "unique_actors": n_actors,
                            "events_count": n_events,
                            "baseline_actors": baseline,
                        },
                        is_audit_sample=False,
                    )
                )

        return candidates
