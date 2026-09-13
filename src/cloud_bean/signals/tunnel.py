"""Proxy tunneling and out-of-band communication channel detector."""

import re
from typing import List

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent


TUNNEL_PATTERNS = [
    re.compile(r"bypass\.blob\.core\.windows\.net", re.IGNORECASE),
    re.compile(r"/etc/hosts", re.IGNORECASE),
    re.compile(r"NO_PROXY", re.IGNORECASE),
    re.compile(r"\?action=edit", re.IGNORECASE),
    re.compile(r"wabi-.*-api\.analysis\.windows\.net", re.IGNORECASE),
    re.compile(r"curl\s+-k\s+-H\s+['\"]Host:", re.IGNORECASE),
]


class ProxyTunnelingDetector:
    """Detects network sandbox evasion, DNS override recipes, and HTTP method abuse."""

    def __init__(self, min_events: int = 1) -> None:
        self.min_events = min_events

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Detect proxy tunneling or egress evasion payloads."""
        flagged_events: List[FleetEvent] = []
        matched_indicators: List[str] = []

        for e in events:
            text_corpus = (
                str(e.payload.get("body", ""))
                + " "
                + str(e.payload.get("body_snippet", ""))
                + " "
                + str(e.payload.get("change_summary", ""))
                + " "
                + str(e.operation or "")
                + " "
                + str(e.target or "")
            )

            matched_for_event = []
            for pat in TUNNEL_PATTERNS:
                m = pat.search(text_corpus)
                if m:
                    matched_for_event.append(m.group(0))

            # Check for HTTP method abuse (modifying state via GET)
            if e.event_type == EventType.resource_write and "action=edit" in text_corpus.lower():
                matched_for_event.append("GET_method_write_abuse")

            if matched_for_event:
                flagged_events.append(e)
                matched_indicators.extend(matched_for_event)

        if len(flagged_events) >= self.min_events:
            actors = sorted({e.actor_id for e in flagged_events})
            targets = sorted({e.target for e in flagged_events if e.target})
            group_id = f"cand_tunnel_{window_start}_{window_end}_{len(flagged_events)}"

            return [
                CandidateGroup(
                    group_id=group_id,
                    trigger_signal="proxy_tunneling_anomaly",
                    window_start=window_start,
                    window_end=window_end,
                    target_resources=targets,
                    actors=actors,
                    event_ids=[e.event_id for e in flagged_events],
                    metrics={
                        "flagged_events_count": len(flagged_events),
                        "matched_indicators": sorted(set(matched_indicators)),
                    },
                    is_audit_sample=False,
                )
            ]

        return []
