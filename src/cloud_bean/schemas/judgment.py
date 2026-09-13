"""Luna Judge response and evaluation models."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from cloud_bean.schemas.evidence import EvidencePacket


class Assessment(str, Enum):
    concerning = "concerning"
    no_concerning_evidence = "no_concerning_evidence"
    insufficient_evidence = "insufficient_evidence"


class ConcerningPattern(str, Enum):
    coordinated_policy_evasion = "coordinated_policy_evasion"
    evaluation_cheating = "evaluation_cheating"
    concealment_or_persistence = "concealment_or_persistence"
    collective_overload = "collective_overload"
    conflicting_actions_sabotage = "conflicting_actions_sabotage"


class BilledUsage(BaseModel):
    """Usage accounting for a model evaluation request."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)


class LunaJudgment(BaseModel):
    """Structured judgment returned by GPT-5.6 Luna."""

    check_key: str = Field(..., min_length=1, description="Deterministic hash of packet, prompt, and model settings")
    packet_id: str = Field(..., min_length=1, description="Evidence packet ID evaluated")
    model: str = Field(default="gpt-5.6-luna", description="Model name and version")
    evaluated_at: str = Field(..., description="ISO-8601 evaluation timestamp")
    assessment: Assessment = Field(..., description="Semantic finding assessment")
    patterns: List[ConcerningPattern] = Field(default_factory=list, description="Specific patterns detected")
    actors: List[str] = Field(default_factory=list, description="Actors identified in the pattern")
    evidence_ids: List[str] = Field(default_factory=list, description="Evidence IDs cited by the judge")
    policy_ids: List[str] = Field(default_factory=list, description="Applicable policy IDs cited")
    observed_actions: List[str] = Field(default_factory=list, description="Factual actions observed")
    missing_context: List[str] = Field(default_factory=list, description="Uncertainties or missing evidence notes")
    explanation: str = Field(default="", description="Justification for the assessment")
    billed_usage: BilledUsage = Field(default_factory=BilledUsage)

    def validate_evidence_references(self, packet: EvidencePacket) -> bool:
        """Reject judgments citing invented evidence IDs not present in the packet."""
        valid_ids = {e.evidence_id for e in packet.chronological_events}
        return all(eid in valid_ids for eid in self.evidence_ids)
