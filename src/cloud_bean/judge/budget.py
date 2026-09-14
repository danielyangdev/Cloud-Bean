"""Budget manager and cost accounting for GPT-5.6 Luna evaluation requests."""

from dataclasses import dataclass
from enum import Enum
import threading
import uuid
from typing import Dict, Optional

from cloud_bean.schemas.budget import BudgetLedger, RateLimits


class ReservationStatus(str, Enum):
    RESERVED = "reserved"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONCURRENCY_LIMIT_EXCEEDED = "concurrency_limit_exceeded"
    CANCELLED = "cancelled"


@dataclass
class ReservationResult:
    """Outcome of a budget reservation attempt."""

    success: bool
    status: ReservationStatus
    reservation_id: Optional[str] = None
    estimated_cost_usd: float = 0.0


class BudgetManager:
    """Manages transactional token spend, cost reservations, and concurrency limits."""

    # Default pricing: $0.25 / 1M prompt tokens, $1.50 / 1M output tokens
    DEFAULT_INPUT_TOKEN_PRICE_USD = 0.25 / 1_000_000.0
    DEFAULT_OUTPUT_TOKEN_PRICE_USD = 1.50 / 1_000_000.0

    def __init__(
        self,
        max_budget_usd: float = 10.00,
        max_concurrent_requests: int = 4,
        input_token_price_usd: Optional[float] = None,
        output_token_price_usd: Optional[float] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.input_price = input_token_price_usd or self.DEFAULT_INPUT_TOKEN_PRICE_USD
        self.output_price = output_token_price_usd or self.DEFAULT_OUTPUT_TOKEN_PRICE_USD

        self._ledger = BudgetLedger(
            max_budget_usd=max_budget_usd,
            spent_usd=0.0,
            reserved_usd=0.0,
            total_checks_dispatched=0,
            checks_completed=0,
            checks_budget_exhausted=0,
            audit_samples_completed=0,
            rate_limits=RateLimits(
                max_concurrent_requests=max_concurrent_requests,
                active_requests=0,
            ),
        )
        # Active reservations mapping: reservation_id -> reserved_amount_usd
        self._reservations: Dict[str, float] = {}

    def get_ledger(self) -> BudgetLedger:
        """Return a snapshot copy of the current budget ledger."""
        with self._lock:
            return self._ledger.model_copy(deep=True)

    def set_max_budget(self, max_budget_usd: float) -> float:
        """Adjust the spend cap and return the previous value.

        Used to demonstrate budget-exhaustion behaviour without restarting the
        process: lowering the cap to current spend leaves no headroom, so the next
        reservations are refused and recorded as skipped rather than silently
        treated as healthy.
        """
        with self._lock:
            previous = self._ledger.max_budget_usd
            self._ledger.max_budget_usd = max_budget_usd
            return previous

    def estimate_cost(
        self,
        prompt_tokens: int,
        output_tokens: int = 512,
    ) -> float:
        """Estimate worst-case cost in USD for given input and output token counts."""
        cost = (prompt_tokens * self.input_price) + (output_tokens * self.output_price)
        return max(0.00001, round(cost, 6))

    def reserve(self, estimated_cost_usd: float) -> ReservationResult:
        """Atomically reserve estimated cost and check rate/budget limits before dispatch."""
        with self._lock:
            # 1. Check concurrency
            if (
                self._ledger.rate_limits.active_requests
                >= self._ledger.rate_limits.max_concurrent_requests
            ):
                return ReservationResult(
                    success=False,
                    status=ReservationStatus.CONCURRENCY_LIMIT_EXCEEDED,
                    estimated_cost_usd=estimated_cost_usd,
                )

            # 2. Check total spend cap (spent + reserved + new_estimate > max_budget)
            projected_total = (
                self._ledger.spent_usd
                + self._ledger.reserved_usd
                + estimated_cost_usd
            )
            if projected_total > self._ledger.max_budget_usd:
                self._ledger.checks_budget_exhausted += 1
                return ReservationResult(
                    success=False,
                    status=ReservationStatus.BUDGET_EXHAUSTED,
                    estimated_cost_usd=estimated_cost_usd,
                )

            # 3. Apply reservation
            reservation_id = f"res_{uuid.uuid4().hex[:12]}"
            self._reservations[reservation_id] = estimated_cost_usd
            self._ledger.reserved_usd = round(
                self._ledger.reserved_usd + estimated_cost_usd, 6
            )
            self._ledger.rate_limits.active_requests += 1
            self._ledger.total_checks_dispatched += 1

            return ReservationResult(
                success=True,
                status=ReservationStatus.RESERVED,
                reservation_id=reservation_id,
                estimated_cost_usd=estimated_cost_usd,
            )

    def reconcile(
        self,
        reservation_id: str,
        actual_cost_usd: float,
        is_audit_sample: bool = False,
    ) -> None:
        """Reconcile reservation after successful model response."""
        with self._lock:
            reserved_amount = self._reservations.pop(reservation_id, 0.0)
            self._ledger.reserved_usd = max(
                0.0, round(self._ledger.reserved_usd - reserved_amount, 6)
            )
            self._ledger.spent_usd = round(
                self._ledger.spent_usd + actual_cost_usd, 6
            )
            self._ledger.rate_limits.active_requests = max(
                0, self._ledger.rate_limits.active_requests - 1
            )
            self._ledger.checks_completed += 1

            if is_audit_sample:
                self._ledger.audit_samples_completed += 1

    def release(self, reservation_id: str) -> None:
        """Release reservation if request was aborted or rejected before sending."""
        with self._lock:
            reserved_amount = self._reservations.pop(reservation_id, 0.0)
            self._ledger.reserved_usd = max(
                0.0, round(self._ledger.reserved_usd - reserved_amount, 6)
            )
            self._ledger.rate_limits.active_requests = max(
                0, self._ledger.rate_limits.active_requests - 1
            )
