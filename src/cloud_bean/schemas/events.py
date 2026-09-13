"""Event models for Cloud-Bean."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    tool_call = "tool_call"
    tool_result = "tool_result"
    message_post = "message_post"
    resource_write = "resource_write"
    resource_read = "resource_read"
    system_event = "system_event"


class FleetEvent(BaseModel):
    """Normalized event emitted by an agent runtime or telemetry sensor."""

    event_id: str = Field(..., min_length=1, description="Deterministic unique event ID")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp")
    uncertainty_seconds: float = Field(default=0.0, ge=0.0, description="Clock uncertainty window in seconds")
    actor_id: str = Field(..., min_length=1, description="Identified agent handle or worker ID")
    task_id: str = Field(..., min_length=1, description="Task context ID")
    session_id: Optional[str] = Field(default=None, description="Optional agent session locator")
    event_type: EventType = Field(..., description="Normalized event type")
    target: str = Field(..., min_length=1, description="Target resource, URI, or tool identifier")
    operation: Optional[str] = Field(default=None, description="Specific operation name")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Structured details or body snippet")
    parent_event_id: Optional[str] = Field(default=None, description="Preceding event ID in causal chain")
    sensor_source: str = Field(default="runtime_sensor", description="Source sensor provenance")
    missing_fields: List[str] = Field(default_factory=list, description="Telemetry fields omitted by sensor")
