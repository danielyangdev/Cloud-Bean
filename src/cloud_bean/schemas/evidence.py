"""Evidence packet models for the Luna Judge."""

from typing import Dict, List
from pydantic import BaseModel, Field


class ChronologicalEvent(BaseModel):
    """An event included as evidence with a stable reference ID."""

    evidence_id: str = Field(..., min_length=1, description="Stable evidence identifier (e.g. ev_01)")
    event_id: str = Field(..., min_length=1, description="Original raw event ID")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp")
    actor_id: str = Field(..., min_length=1, description="Actor who performed the action")
    action_type: str = Field(..., min_length=1, description="Action or tool type")
    summary: str = Field(default="", description="Brief factual summary of the action")
    snippet: str = Field(default="", description="Verbatim payload body or message snippet")


class ActorContext(BaseModel):
    """Context and declared scope of an actor in an evidence packet."""

    actor_id: str = Field(..., min_length=1)
    declared_role: str = Field(default="")
    task_family: str = Field(default="")


class PolicyStatement(BaseModel):
    """Authoritative task policy or constraint."""

    policy_id: str = Field(..., min_length=1)
    rule: str = Field(..., min_length=1)


class EvidencePacket(BaseModel):
    """Bounded packet dispatched to Luna for semantic judgment."""

    packet_id: str = Field(..., min_length=1, description="Unique evidence packet ID")
    group_id: str = Field(..., min_length=1, description="Originating candidate group ID")
    created_at: str = Field(..., description="ISO-8601 creation timestamp")
    token_count_estimate: int = Field(default=0, ge=0, description="Estimated token count of this packet")
    trigger_reasons: List[str] = Field(default_factory=list, description="Reasons flagged by signals")
    actors: List[ActorContext] = Field(default_factory=list, description="Actor profiles in this packet")
    applicable_policies: List[PolicyStatement] = Field(default_factory=list, description="Explicit trusted policies")
    chronological_events: List[ChronologicalEvent] = Field(
        default_factory=list, description="Ordered chronological evidence events"
    )
    missing_context_flags: Dict[str, bool] = Field(
        default_factory=dict, description="Flags for absent telemetry or permissions"
    )
