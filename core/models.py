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
    """Lo que el motor recibe para evaluar."""
    event_id: str
    tenant_id: str
    error_code: str
    attempt_count: int
    amount: float
    currency: str = "USD"
    customer_risk_score: float = 0.0

@dataclass
class DunningAction:
    """Lo que el motor escupe como decisión."""
    action_type: ActionType
    reason: str
    scheduled_for: Optional[datetime] = None