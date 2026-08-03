from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Optional, List


class PaymentErrorData(BaseModel):
    """PaymentErrorData contains details for a failed payment event.

    Args:
        customer_id: Customer ID in the source platform.
        invoice_id: Invoice or subscription ID to charge.
        amount: Amount of failed payment.
        currency: Currency code (e.g: USD, EUR).
        error_code: Reason for failure (e.g: insufficient_funds, card_expired).
        attempt_count: Current attempt number.
    """

    customer_id: str = Field(..., description="Customer ID in the source platform")
    invoice_id: str = Field(..., description="Invoice or subscription ID to charge")
    amount: float = Field(..., gt=0, description="Amount of failed payment")
    currency: str = Field(
        ..., min_length=3, max_length=3, description="Currency code (e.g: USD, EUR)"
    )
    error_code: str = Field(
        ..., description="Reason for failure (e.g: insufficient_funds, card_expired)"
    )
    attempt_count: int = Field(default=1, ge=1, description="Current attempt number")


class WebhookIngestPayload(BaseModel):
    """Payload for ingesting webhook events about failed payments.

    This model represents the data sent by external payment providers when a
    payment attempt fails. It includes an idempotency event_id, the tenant
    identifier for the merchant, a timezone-aware timestamp and the
    PaymentErrorData describing the failure.

    Attributes:
        event_id: Unique ID to avoid processing the same event twice.
        tenant_id: ID of our customer (the e-commerce/SaaS) that owns the event.
        timestamp: Time when the event occurred (timezone-aware UTC by default).
        data: PaymentErrorData with details about the failed payment.
    """

    event_id: str = Field(
        ...,
        description="Unique ID to avoid processing the same event twice (idempotency)",
    )
    tenant_id: str = Field(..., description="ID of our customer (the e-commerce/SaaS)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: PaymentErrorData

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_timezone(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class DunningRulesConfig(BaseModel):
    """Configuration for dunning retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts for failed payments.
        hard_errors: Error codes considered non-retryable hard failures.
        grace_period_days: Number of days to wait before the first retry.
        strategy: Retry schedule strategy, one of exponential, linear, or fixed.
    """

    max_attempts: int = Field(
        default=3, ge=1, le=10, description="Max number of retry attempts"
    )
    hard_errors: List[str] = Field(
        default=["card_stolen", "fraud_suspected", "account_closed"],
        description="List of error codes considered hard errors that should not be retried",
    )
    grace_period_days: int = Field(
        default=1, ge=0, description="Days of grace before the first retry"
    )
    strategy: str = Field(
        default="exponential",
        pattern="^(exponential|linear|fixed)$",
        description="Type of date calculation",
    )


class TenantConfigPayload(BaseModel):
    """Tenant-specific dunning configuration payload.

    Attributes:
        tenant_id: B2B tenant identifier.
        is_active: Whether dunning is enabled for this tenant.
        rules: Dunning rules configuration for the tenant.
    """

    tenant_id: str = Field(..., description="B2B tenant identifier")
    is_active: bool = Field(default=True)
    rules: DunningRulesConfig
