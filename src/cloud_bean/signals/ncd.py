"""Cross-Agent Normalized Compression Distance (NCD) and Mutual Information Detector.

Implements parameter-free information-theoretic detection of semantic collusion
based on Kolmogorov complexity approximated via real-time compression algorithms.
"""

from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Tuple
import zlib

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


def compressed_size(data: str) -> int:
    """Compute compressed byte length using standard zlib compression."""
    return len(zlib.compress(data.encode("utf-8"), level=6))


def compute_ncd(x: str, y: str) -> float:
    """Calculate Normalized Compression Distance NCD(x, y) = (C(xy) - min(C(x), C(y))) / max(C(x), C(y))."""
    if not x or not y:
        return 1.0

    cx = compressed_size(x)
    cy = compressed_size(y)
    cxy = compressed_size(x + " " + y)

    min_c = min(cx, cy)
    max_c = max(cx, cy)

    if max_c == 0:
        return 0.0

    ncd = (cxy - min_c) / max_c
    return max(0.0, min(1.0, ncd))


class CrossAgentNCDDetector:
    """Detects hidden semantic mutual information and cross-task collusion via Normalized Compression Distance."""

    def __init__(
        self,
        ncd_threshold: float = 0.45,
        min_payload_len: int = 50,
    ) -> None:
        self.ncd_threshold = ncd_threshold
        self.min_payload_len = min_payload_len

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate cross-agent pairs for abnormal compression distance drops."""
        # Aggregate text emitted by each agent across tasks
        actor_corpus: Dict[str, str] = defaultdict(str)
        actor_events: Dict[str, List[str]] = defaultdict(list)
        actor_tasks: Dict[str, set] = defaultdict(set)
        actor_targets: Dict[str, set] = defaultdict(set)

        for e in events:
            body = (
                str(e.payload.get("body", ""))
                + " "
                + str(e.payload.get("body_snippet", ""))
                + " "
                + str(e.payload.get("change_summary", ""))
            )
            if len(body.strip()) >= self.min_payload_len:
                actor_corpus[e.actor_id] += body + "\n"
                actor_events[e.actor_id].append(e.event_id)
                actor_tasks[e.actor_id].add(e.task_id)
                if e.target:
                    actor_targets[e.actor_id].add(e.target)

        actors = [a for a in actor_corpus if len(actor_corpus[a]) >= self.min_payload_len]
        if len(actors) < 2:
            return []

        candidates: List[CandidateGroup] = []

        # Check all agent pairs
        for a1, a2 in combinations(actors, 2):
            # Only compare if they are working on separate tasks
            if not actor_tasks[a1].isdisjoint(actor_tasks[a2]):
                continue

            ncd = compute_ncd(actor_corpus[a1], actor_corpus[a2])

            if ncd < self.ncd_threshold:
                targets = sorted(actor_targets[a1] | actor_targets[a2])
                all_event_ids = sorted(set(actor_events[a1] + actor_events[a2]))
                group_id = f"cand_ncd_{a1}_{a2}_{window_start}_{window_end}"

                candidates.append(
                    CandidateGroup(
                        group_id=group_id,
                        trigger_signal="compression_distance_anomaly",
                        window_start=window_start,
                        window_end=window_end,
                        target_resources=targets,
                        actors=sorted([a1, a2]),
                        event_ids=all_event_ids,
                        metrics={
                            "normalized_compression_distance": round(ncd, 4),
                            "ncd_threshold": self.ncd_threshold,
                            "actor_1_len": len(actor_corpus[a1]),
                            "actor_2_len": len(actor_corpus[a2]),
                        },
                        is_audit_sample=False,
                    )
                )

        return candidates
