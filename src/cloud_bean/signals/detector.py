"""Fleet signal engine coordinating all metadata heuristics."""

from typing import List, Optional

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent
from cloud_bean.signals.artifact import SharedArtifactDetector
from cloud_bean.signals.audit import AuditSampler
from cloud_bean.signals.burst import SynchronizedBurstDetector
from cloud_bean.signals.conflict import ConflictingWritesDetector
from cloud_bean.signals.hub import EmergingHubDetector
from cloud_bean.signals.latency import AdoptionLatencyDetector
from cloud_bean.signals.ncd import CrossAgentNCDDetector
from cloud_bean.signals.overload import CollectiveOverloadDetector
from cloud_bean.signals.token_distribution import TokenDistributionAnalyzer
from cloud_bean.signals.tunnel import ProxyTunnelingDetector


class FleetSignalEngine:
    """Orchestrates heuristic signals over time-windowed event streams."""

    def __init__(
        self,
        hub_detector: Optional[EmergingHubDetector] = None,
        conflict_detector: Optional[ConflictingWritesDetector] = None,
        artifact_detector: Optional[SharedArtifactDetector] = None,
        overload_detector: Optional[CollectiveOverloadDetector] = None,
        burst_detector: Optional[SynchronizedBurstDetector] = None,
        latency_detector: Optional[AdoptionLatencyDetector] = None,
        tunnel_detector: Optional[ProxyTunnelingDetector] = None,
        token_analyzer: Optional[TokenDistributionAnalyzer] = None,
        ncd_detector: Optional[CrossAgentNCDDetector] = None,
        audit_sampler: Optional[AuditSampler] = None,
    ) -> None:
        self.hub_detector = hub_detector or EmergingHubDetector()
        self.conflict_detector = conflict_detector or ConflictingWritesDetector()
        self.artifact_detector = artifact_detector or SharedArtifactDetector()
        self.overload_detector = overload_detector or CollectiveOverloadDetector()
        self.burst_detector = burst_detector or SynchronizedBurstDetector()
        self.latency_detector = latency_detector or AdoptionLatencyDetector()
        self.tunnel_detector = tunnel_detector or ProxyTunnelingDetector()
        self.token_analyzer = token_analyzer or TokenDistributionAnalyzer()
        self.ncd_detector = ncd_detector or CrossAgentNCDDetector()
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

        # 5. Synchronized burstiness
        candidates.extend(self.burst_detector.evaluate_window(events, window_start, window_end))

        # 6. Write-to-read adoption latency
        candidates.extend(self.latency_detector.evaluate_window(events, window_start, window_end))

        # 7. Proxy tunneling anomaly
        candidates.extend(self.tunnel_detector.evaluate_window(events, window_start, window_end))

        # 8. Token & word distribution anomaly
        candidates.extend(self.token_analyzer.evaluate_window(events, window_start, window_end))

        # 9. Cross-agent Normalized Compression Distance (NCD)
        candidates.extend(self.ncd_detector.evaluate_window(events, window_start, window_end))

        # 10. Audit sampling if no signals flagged this window
        if not candidates and enable_audit:
            audit_cands = self.audit_sampler.sample_window_if_eligible(
                events, window_start, window_end
            )
            candidates.extend(audit_cands)

        return candidates
