"""Finding and alert models."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from cloud_bean.schemas.judgment import Assessment, ConcerningPattern


class FindingStatus(str, Enum):
    active = "active"
    resolved = "resolved"
    suppressed = "suppressed"


class FindingSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Finding(BaseModel):
    """A durable, deduplicated finding derived from an accepted judgment or explicit rule violation."""

    finding_id: str = Field(..., min_length=1, description="Unique deterministic finding identifier")
    check_key: str = Field(..., min_length=1, description="Check key reference")
    status: FindingStatus = Field(default=FindingStatus.active)
    severity: FindingSeverity = Field(default=FindingSeverity.high)
    pattern: ConcerningPattern = Field(...)
    assessment: Assessment = Field(default=Assessment.concerning)
    actors: List[str] = Field(default_factory=list, description="Actors implicated")
    target_resources: List[str] = Field(default_factory=list, description="Target resources affected")
    first_evidence_time: str = Field(..., description="Timestamp of the earliest cited evidence")
    detected_at: str = Field(..., description="Timestamp when finding was recorded")
    explanation: str = Field(default="", description="Explanation derived from judgment")
    evidence_ids: List[str] = Field(default_factory=list, description="Cited evidence IDs")
    raw_judgment_ref: str = Field(..., min_length=1, description="Hash reference to persisted accepted judgment")
    is_audit_sample: bool = Field(default=False, description="Whether finding arose from an audit sample")
