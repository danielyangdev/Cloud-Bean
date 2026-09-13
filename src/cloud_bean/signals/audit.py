"""Audit sampler for reproducible unflagged candidate sampling."""

import hashlib
from typing import List

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


class AuditSampler:
    """Deterministically samples unflagged multi-agent windows for selection miss auditing."""

    def __init__(
        self,
        sample_rate_mod: int = 10,
        seed: str = "audit_seed_v1",
    ) -> None:
        self.sample_rate_mod = sample_rate_mod
        self.seed = seed

    def should_sample(self, group_id: str) -> bool:
        """Deterministically determine if a candidate window should be sampled."""
        key = f"{group_id}{self.seed}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        # Take the integer value of the first 8 hex characters
        val = int(digest[:8], 16)
        return (val % self.sample_rate_mod) == 0

    def sample_window_if_eligible(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Create an audit CandidateGroup if window has >= 2 actors and hash matches."""
        actors = sorted({e.actor_id for e in events})
        if len(actors) < 2:
            return []

        targets = sorted({e.target for e in events if e.target})
        group_id = f"cand_audit_{window_start}_{window_end}_{len(events)}"

        if self.should_sample(group_id):
            return [
                CandidateGroup(
                    group_id=group_id,
                    trigger_signal="audit_sample",
                    window_start=window_start,
                    window_end=window_end,
                    target_resources=targets,
                    actors=actors,
                    event_ids=[e.event_id for e in events],
                    metrics={
                        "sample_rate_mod": self.sample_rate_mod,
                        "unique_actors": len(actors),
                        "total_events": len(events),
                    },
                    is_audit_sample=True,
                )
            ]

        return []
