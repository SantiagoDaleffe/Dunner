from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ActionType(Enum):
    RETRY = "RETRY"
    CANCEL = "CANCEL"
    ALERT = "ALERT"


@dataclass
class PaymentEvent:
    """Represents a payment-processing event associated with a failed or delayed payment.

    Attributes:
        event_id: Unique identifier for the payment event.
        tenant_id: Identifier of the tenant or merchant owning the event.
        error_code: Error code describing the payment failure or issue.
        attempt_count: Number of payment attempts already made for this event.
        amount: Payment amount in the specified currency.
        currency: ISO currency code for the payment amount. Defaults to USD.
        customer_risk_score: Risk score for the customer, used in dunning decisions.
    """

    event_id: str
    tenant_id: str
    error_code: str
    attempt_count: int
    amount: float
    currency: str = "USD"
    customer_risk_score: float = 0.0


@dataclass
class DunningAction:
    """Represents a suggested follow-up action for a payment event.

    Attributes:
        action_type: Type of action to execute, such as retry, cancel, or alert.
        reason: Human-readable explanation for the action.
        scheduled_for: Optional timestamp indicating when the action should be executed.
    """

    action_type: ActionType
    reason: str
    scheduled_for: Optional[datetime] = None
