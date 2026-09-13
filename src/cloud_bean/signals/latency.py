"""Write-to-read cross-agent adoption latency detector."""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent


def _parse_ts(ts: str) -> float:
    """Parse ISO-8601 timestamp string into POSIX epoch seconds."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.timestamp()


class AdoptionLatencyDetector:
    """Detects rapid cross-agent consumption of shared answers or bypass tokens."""

    def __init__(
        self,
        max_adoption_seconds: float = 180.0,
        min_rapid_adoptions: int = 2,
    ) -> None:
        self.max_adoption_seconds = max_adoption_seconds
        self.min_rapid_adoptions = min_rapid_adoptions

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate resource interactions for rapid cross-agent write-to-read adoption."""
        target_events: Dict[str, List[FleetEvent]] = defaultdict(list)
        for e in events:
            if e.target and e.event_type in (
                EventType.resource_write,
                EventType.resource_read,
                EventType.message_post,
            ):
                target_events[e.target].append(e)

        candidates: List[CandidateGroup] = []

        for target, ev_list in target_events.items():
            sorted_evs = sorted(ev_list, key=lambda e: _parse_ts(e.timestamp))
            if len(sorted_evs) < 2:
                continue

            rapid_adoptions = 0
            involved_actors = set()
            involved_event_ids = set()

            for i in range(len(sorted_evs) - 1):
                e1 = sorted_evs[i]
                e2 = sorted_evs[i + 1]

                is_e1_write = e1.event_type in (EventType.resource_write, EventType.message_post)
                is_e2_read_or_write = e2.event_type in (EventType.resource_read, EventType.resource_write)

                if is_e1_write and is_e2_read_or_write and e1.actor_id != e2.actor_id:
                    dt = _parse_ts(e2.timestamp) - _parse_ts(e1.timestamp)
                    if 0 <= dt <= self.max_adoption_seconds:
                        rapid_adoptions += 1
                        involved_actors.add(e1.actor_id)
                        involved_actors.add(e2.actor_id)
                        involved_event_ids.add(e1.event_id)
                        involved_event_ids.add(e2.event_id)

            if rapid_adoptions >= self.min_rapid_adoptions:
                group_id = f"cand_latency_{abs(hash(target)) % 1000000}_{window_start}_{window_end}"
                candidates.append(
                    CandidateGroup(
                        group_id=group_id,
                        trigger_signal="rapid_adoption_latency",
                        window_start=window_start,
                        window_end=window_end,
                        target_resources=[target],
                        actors=sorted(involved_actors),
                        event_ids=sorted(involved_event_ids),
                        metrics={
                            "rapid_adoptions": rapid_adoptions,
                            "max_adoption_threshold_seconds": self.max_adoption_seconds,
                        },
                        is_audit_sample=False,
                    )
                )

        return candidates
