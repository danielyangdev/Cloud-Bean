"""Fleet signal engine coordinating all metadata heuristics."""

from typing import List, Optional

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.signals.artifact import SharedArtifactDetector
from cloud_bean.signals.audit import AuditSampler
from cloud_bean.signals.conflict import ConflictingWritesDetector
from cloud_bean.signals.hub import EmergingHubDetector
from cloud_bean.signals.overload import CollectiveOverloadDetector


class FleetSignalEngine:
    """Orchestrates heuristic signals over time-windowed event streams."""

    def __init__(
        self,
        hub_detector: Optional[EmergingHubDetector] = None,
        conflict_detector: Optional[ConflictingWritesDetector] = None,
        artifact_detector: Optional[SharedArtifactDetector] = None,
        overload_detector: Optional[CollectiveOverloadDetector] = None,
        audit_sampler: Optional[AuditSampler] = None,
    ) -> None:
        self.hub_detector = hub_detector or EmergingHubDetector()
        self.conflict_detector = conflict_detector or ConflictingWritesDetector()
        self.artifact_detector = artifact_detector or SharedArtifactDetector()
        self.overload_detector = overload_detector or CollectiveOverloadDetector()
        self.audit_sampler = audit_sampler or AuditSampler()

    def process_events(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
        enable_audit: bool = True,
    ) -> List[CandidateGroup]:
        """Run all detectors over an event window and return candidate groups."""
        candidates: List[CandidateGroup] = []

        # 1. Emerging hubs
        candidates.extend(self.hub_detector.evaluate_window(events, window_start, window_end))

        # 2. Conflicting writes
        candidates.extend(self.conflict_detector.evaluate_window(events, window_start, window_end))

        # 3. Shared artifact reuse
        candidates.extend(self.artifact_detector.evaluate_window(events, window_start, window_end))

        # 4. Collective overload
        candidates.extend(self.overload_detector.evaluate_window(events, window_start, window_end))

        # 5. Audit sampling if no signals flagged this window
        if not candidates and enable_audit:
            audit_cands = self.audit_sampler.sample_window_if_eligible(
                events, window_start, window_end
            )
            candidates.extend(audit_cands)

        return candidates
