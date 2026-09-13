"""Bounded Evidence Packet Builder for GPT-5.6 Luna Judge."""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional, Set

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.schemas.evidence import (
    ActorContext,
    ChronologicalEvent,
    EvidencePacket,
    PolicyStatement,
)


def _parse_ts(ts: str) -> float:
    """Parse ISO-8601 timestamp string into POSIX epoch seconds."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.timestamp()


def _estimate_tokens(text: str) -> int:
    """Fast conservative heuristic for token counting (~4 characters per token)."""
    return max(1, (len(text) + 3) // 4)


class EvidenceSelector:
    """Assembles and bounds multi-agent interaction evidence into EvidencePacket objects."""

    def __init__(self, max_snippet_chars: int = 600) -> None:
        self.max_snippet_chars = max_snippet_chars

    def _summarize_event(self, event: FleetEvent) -> str:
        """Generate a concise, factual summary of the event."""
        op = event.operation
        target = event.target or "unspecified_resource"

        if event.event_type == EventType.resource_write:
            return f"Saved revision to {target}" if not op else f"{op} on {target}"
        elif event.event_type == EventType.resource_read:
            return f"Read from {target}" if not op else f"{op} on {target}"
        elif event.event_type == EventType.message_post:
            return f"Posted message to {target}" if not op else f"{op} to {target}"
        elif event.event_type == EventType.tool_call:
            return f"Called tool {op or target}"
        elif event.event_type == EventType.tool_result:
            return f"Received tool result from {target}"
        elif event.event_type == EventType.system_event:
            return f"System event: {op or target}"
        return f"{event.event_type.value} on {target}"

    def _extract_snippet(self, event: FleetEvent) -> str:
        """Extract and bound text snippet from payload."""
        payload = event.payload
        snippet = (
            payload.get("body_snippet")
            or payload.get("body")
            or payload.get("message")
            or payload.get("text")
            or payload.get("change_summary")
            or ""
        )
        if not snippet and "args" in payload:
            snippet = str(payload["args"])

        snippet_str = str(snippet)
        if len(snippet_str) > self.max_snippet_chars:
            snippet_str = snippet_str[: self.max_snippet_chars] + "... [truncated]"
        return snippet_str

    def build_packet(
        self,
        candidate: CandidateGroup,
        events: List[FleetEvent],
        policies: Optional[List[PolicyStatement]] = None,
        actor_contexts: Optional[List[ActorContext]] = None,
        max_tokens: int = 8000,
    ) -> EvidencePacket:
        """Assemble, order, and token-bound evidence into an EvidencePacket."""
        # 1. Filter events relevant to this candidate
        cand_event_id_set: Set[str] = set(candidate.event_ids)
        if cand_event_id_set:
            relevant_events = [e for e in events if e.event_id in cand_event_id_set]
        else:
            relevant_events = list(events)

        # 2. Sort chronologically
        sorted_events = sorted(relevant_events, key=lambda e: _parse_ts(e.timestamp))

        # 3. Resolve actor contexts
        resolved_actors: List[ActorContext] = []
        if actor_contexts:
            resolved_actors = list(actor_contexts)
        else:
            # Derive from candidate actors or observed event actors
            actor_ids = sorted(
                set(candidate.actors) | {e.actor_id for e in sorted_events}
            )
            for aid in actor_ids:
                resolved_actors.append(ActorContext(actor_id=aid))

        # 4. Resolve policies
        applicable_policies: List[PolicyStatement] = (
            list(policies) if policies is not None else []
        )

        # Base token overhead for packet metadata, trigger reasons, actors, policies
        scaffolding_text = (
            candidate.group_id
            + candidate.trigger_signal
            + "".join(a.actor_id + a.declared_role for a in resolved_actors)
            + "".join(p.policy_id + p.rule for p in applicable_policies)
        )
        running_tokens = _estimate_tokens(scaffolding_text) + 50

        # 5. Pack chronological events within token budget
        selected_evidence_events: List[ChronologicalEvent] = []
        omitted_events = False

        for i, event in enumerate(sorted_events):
            summary = self._summarize_event(event)
            snippet = self._extract_snippet(event)
            evidence_id = f"ev_{i + 1:02d}"

            event_token_cost = (
                _estimate_tokens(summary)
                + _estimate_tokens(snippet)
                + _estimate_tokens(event.actor_id + event.timestamp + event.event_type.value)
                + 10
            )

            if running_tokens + event_token_cost > max_tokens:
                omitted_events = True
                break

            running_tokens += event_token_cost
            selected_evidence_events.append(
                ChronologicalEvent(
                    evidence_id=evidence_id,
                    event_id=event.event_id,
                    timestamp=event.timestamp,
                    actor_id=event.actor_id,
                    action_type=event.event_type.value,
                    summary=summary,
                    snippet=snippet,
                )
            )

        # 6. Analyze missing context flags
        missing_reads = any(
            "reads" in e.missing_fields for e in relevant_events
        )
        unverified_execution = any(
            "execution_receipt" in e.missing_fields for e in relevant_events
        )
        missing_permissions = policies is None or len(policies) == 0

        missing_context_flags: Dict[str, bool] = {
            "missing_reads": missing_reads,
            "missing_permissions": missing_permissions,
            "unverified_execution": unverified_execution,
            "omitted_events": omitted_events,
        }

        # 7. Form deterministic packet ID
        hash_seed = f"{candidate.group_id}:{len(selected_evidence_events)}:{running_tokens}"
        packet_id = f"pkt_{hashlib.sha256(hash_seed.encode('utf-8')).hexdigest()[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        trigger_reasons = [
            f"Flagged by signal heuristic: {candidate.trigger_signal}"
        ]
        if candidate.metrics:
            trigger_reasons.append(f"Signal metrics: {candidate.metrics}")

        return EvidencePacket(
            packet_id=packet_id,
            group_id=candidate.group_id,
            created_at=now_iso,
            token_count_estimate=running_tokens,
            trigger_reasons=trigger_reasons,
            actors=resolved_actors,
            applicable_policies=applicable_policies,
            chronological_events=selected_evidence_events,
            missing_context_flags=missing_context_flags,
        )
