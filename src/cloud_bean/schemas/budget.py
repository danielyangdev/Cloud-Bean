"""Budget ledger and rate limit models."""

from pydantic import BaseModel, Field


class RateLimits(BaseModel):
    """Runtime concurrency and rate controls."""

    max_concurrent_requests: int = Field(default=4, ge=1, description="Maximum concurrent model requests")
    active_requests: int = Field(default=0, ge=0, description="Currently in-flight model requests")


class BudgetLedger(BaseModel):
    """Spend, reservation, and audit ledger for model checks."""

    max_budget_usd: float = Field(default=10.00, ge=0.0, description="Deployment hard spend limit")
    spent_usd: float = Field(default=0.0, ge=0.0, description="Total billed spend reconciled")
    reserved_usd: float = Field(default=0.0, ge=0.0, description="Currently reserved spend for active requests")
    total_checks_dispatched: int = Field(default=0, ge=0)
    checks_completed: int = Field(default=0, ge=0)
    checks_budget_exhausted: int = Field(default=0, ge=0)
    audit_samples_completed: int = Field(default=0, ge=0)
    rate_limits: RateLimits = Field(default_factory=RateLimits)
