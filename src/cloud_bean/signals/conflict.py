"""Conflicting writes and rapid reversion detector."""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent


def _parse_ts(ts: str) -> float:
    """Parse ISO-8601 timestamp string into POSIX epoch seconds."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.timestamp()


class ConflictingWritesDetector:
    """Detects rapid overwrite battles or alternating edits on shared resources."""

    def __init__(
        self,
        rapid_delta_seconds: float = 120.0,
        min_rapid_alternating_edits: int = 3,
        reversion_window_seconds: float = 300.0,
        min_recreations: int = 2,
    ) -> None:
        self.rapid_delta_seconds = rapid_delta_seconds
        self.min_rapid_alternating_edits = min_rapid_alternating_edits
        self.reversion_window_seconds = reversion_window_seconds
        self.min_recreations = min_recreations

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate a window of events for conflicting writes."""
        # Filter for write/mutation events
        write_events: Dict[str, List[FleetEvent]] = defaultdict(list)
        for e in events:
            if e.event_type in (EventType.resource_write, EventType.system_event) and e.target:
                write_events[e.target].append(e)

        candidates: List[CandidateGroup] = []
        for target, ev_list in write_events.items():
            # Sort chronologically
            sorted_evs = sorted(ev_list, key=lambda x: _parse_ts(x.timestamp))
            if len(sorted_evs) < 2:
                continue

            rapid_alternating_count = 0
            recreation_count = 0
            involved_actors = set()
            involved_event_ids = set()

            for i in range(len(sorted_evs) - 1):
                e1 = sorted_evs[i]
                e2 = sorted_evs[i + 1]

                t1 = _parse_ts(e1.timestamp)
                t2 = _parse_ts(e2.timestamp)

                # Check 1: Rapid alternating edits
                if e1.actor_id != e2.actor_id and abs(t2 - t1) <= self.rapid_delta_seconds:
                    rapid_alternating_count += 1
                    involved_actors.add(e1.actor_id)
                    involved_actors.add(e2.actor_id)
                    involved_event_ids.add(e1.event_id)
                    involved_event_ids.add(e2.event_id)

                # Check 2: Deletion followed by recreation by different actor
                is_e1_deletion = "delete" in (e1.operation or "") or e1.payload.get("event_type") == "delete"
                is_e2_write = e2.operation in ("save_revision", None) and e2.payload.get("event_type") != "delete"
                if is_e1_deletion and is_e2_write and e1.actor_id != e2.actor_id and abs(t2 - t1) <= self.reversion_window_seconds:
                    recreation_count += 1
                    involved_actors.add(e1.actor_id)
                    involved_actors.add(e2.actor_id)
                    involved_event_ids.add(e1.event_id)
                    involved_event_ids.add(e2.event_id)

            if rapid_alternating_count >= self.min_rapid_alternating_edits or recreation_count >= self.min_recreations:
                group_id = f"cand_conflict_{abs(hash(target)) % 1000000}_{window_start}_{window_end}"
                candidates.append(
                    CandidateGroup(
                        group_id=group_id,
                        trigger_signal="conflicting_writes",
                        window_start=window_start,
                        window_end=window_end,
                        target_resources=[target],
                        actors=sorted(involved_actors),
                        event_ids=sorted(involved_event_ids),
                        metrics={
                            "rapid_overwrites": rapid_alternating_count,
                            "recreations_after_delete": recreation_count,
                            "delta_threshold_seconds": self.rapid_delta_seconds,
                        },
                        is_audit_sample=False,
                    )
                )

        return candidates
