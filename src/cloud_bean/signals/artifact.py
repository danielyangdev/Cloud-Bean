"""Shared artifact and payload hash detector."""

from collections import defaultdict
import hashlib
from typing import Dict, List

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


class SharedArtifactDetector:
    """Detects reuse of identical non-trivial payload hashes across distinct tasks or agents."""

    def __init__(
        self,
        min_tasks: int = 2,
        min_body_len: int = 32,
    ) -> None:
        self.min_tasks = min_tasks
        self.min_body_len = min_body_len

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate a window of events for shared artifacts."""
        hash_events: Dict[str, List[FleetEvent]] = defaultdict(list)

        for event in events:
            sha = event.payload.get("body_sha256")
            body_len = event.payload.get("body_len")

            if not sha and "body" in event.payload:
                body = str(event.payload["body"])
                if len(body) >= self.min_body_len:
                    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
                    body_len = len(body)

            if not sha:
                continue

            # Ensure payload is non-trivial length
            if body_len is not None and body_len < self.min_body_len:
                continue

            hash_events[sha].append(event)

        candidates: List[CandidateGroup] = []
        for sha, ev_list in hash_events.items():
            tasks = {e.task_id for e in ev_list}
            actors = {e.actor_id for e in ev_list}
            targets = {e.target for e in ev_list if e.target}

            if len(tasks) >= self.min_tasks:
                group_id = f"cand_artifact_{sha[:12]}_{window_start}_{window_end}"
                candidates.append(
                    CandidateGroup(
                        group_id=group_id,
                        trigger_signal="shared_artifact_reuse",
                        window_start=window_start,
                        window_end=window_end,
                        target_resources=sorted(targets),
                        actors=sorted(actors),
                        event_ids=[e.event_id for e in ev_list],
                        metrics={
                            "shared_hash": sha,
                            "distinct_tasks": len(tasks),
                            "distinct_actors": len(actors),
                            "matching_events": len(ev_list),
                            "shared_artifact_matches": len(ev_list),
                        },
                        is_audit_sample=False,
                    )
                )

        return candidates
