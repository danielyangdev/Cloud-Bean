"""Candidate group models emitted by signal workers."""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class CandidateGroup(BaseModel):
    """A cluster of related agent interactions flagged by metadata signals for evidence assembly."""

    group_id: str = Field(..., min_length=1, description="Unique candidate group ID")
    trigger_signal: str = Field(..., min_length=1, description="Signal heuristic that triggered selection")
    window_start: str = Field(..., description="ISO-8601 window start")
    window_end: str = Field(..., description="ISO-8601 window end")
    target_resources: List[str] = Field(default_factory=list, description="Target resources involved")
    actors: List[str] = Field(default_factory=list, description="Distinct actor IDs involved")
    event_ids: List[str] = Field(default_factory=list, description="Event IDs in the candidate window")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Calculated heuristic metrics")
    is_audit_sample: bool = Field(default=False, description="True if selected via reproducible unflagged sampling")
