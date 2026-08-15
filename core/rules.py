from typing import Protocol, Optional, List
from datetime import datetime, timedelta, timezone
from core.models import PaymentEvent, DunningAction, ActionType


class DunningRule(Protocol):
    """Protocol for dunning rules.

    Implementations should provide an evaluate method that inspects a
    PaymentEvent and returns an optional DunningAction describing the
    next step (retry, cancel, etc.).
    """

    def evaluate(self, event: PaymentEvent) -> Optional[DunningAction]:
        """Evaluate the given payment event.

        Args:
            event (PaymentEvent): The payment event to evaluate.

        Returns:
            Optional[DunningAction]: A DunningAction if an action is
                required, otherwise None.
        """
        pass


class HardDeclineRule:
    """Rule that cancels a subscription when a fatal error code occurs.

    fatal_errors is a list of error codes that are considered unrecoverable.
    """

    def __init__(self, fatal_errors: List[str]):
        """Initialize the rule.

        Args:
            fatal_errors (List[str]): Error codes that trigger cancellation.
        """
        self.fatal_errors = fatal_errors

    def evaluate(self, event: PaymentEvent) -> Optional[DunningAction]:
        """Return a cancel action if the event error code is fatal.

        Args:
            event (PaymentEvent): The payment event to inspect.

        Returns:
            Optional[DunningAction]: CANCEL action when error is fatal, 
                otherwise None.
        """
        if event.error_code in self.fatal_errors:
            return DunningAction(
                action_type=ActionType.CANCEL,
                reason=f"Fatal error code detected: {event.error_code}",
            )
        return None


class MaxAttemptsRule:
    """Rule that cancels after a configured number of attempts."""

    def __init__(self, max_attempts: int):
        """Initialize the rule.

        Args:
            max_attempts (int): Maximum number of retry attempts allowed.
        """
        self.max_attempts = max_attempts

    def evaluate(self, event: PaymentEvent) -> Optional[DunningAction]:
        """Return a cancel action when the attempt limit has been reached.

        Args:
            event (PaymentEvent): The payment event containing attempt count.

        Returns:
            Optional[DunningAction]: CANCEL action if attempts exhausted,
                otherwise None.
        """
        if event.attempt_count >= self.max_attempts:
            return DunningAction(
                action_type=ActionType.CANCEL,
                reason=f"Max attempts ({self.max_attempts}) reached.",
            )
        return None
    
class HighValueAlertRule:
    def __init__(self, threshold_amount: float = 1000.0):
        self.threshold_amount = threshold_amount

    def evaluate(self, event: PaymentEvent) -> Optional[DunningAction]:
        if event.amount >= self.threshold_amount:
            return DunningAction(
                action_type=ActionType.ALERT,
                reason=f"High-value payment failed ({event.amount} {event.currency}). Requires manual intervention."
            )
        return None
    
class WeekendSkipRule:
    def evaluate(self, event: PaymentEvent) -> Optional[DunningAction]:
        # Esta regla actúa modificando o evaluando la fecha calculada previamente.
        # Si el reintento cae domingo (weekday() == 6), lo patea al lunes.
        # (Se suele aplicar después del cálculo exponencial).
        return None  # La dejamos lista para integrar en el flujo del engine si se requiere.


class ExponentialBackoffRule:
    """Rule that schedules retries using exponential backoff.

    The delay is base_hours * 2^(attempt_count - 1) and is capped to max_days.
    """

    def __init__(self, base_hours: int = 24, max_days: int = 7):
        """Initialize the exponential backoff rule.

        Args:
            base_hours (int, optional): Base delay in hours. Defaults to 24.
            max_days (int, optional): Maximum delay cap in days. Defaults to 7.
        """
        self.base_hours = base_hours
        self.max_days = max_days

    def evaluate(self, event: PaymentEvent) -> Optional[DunningAction]:
        """Schedule the next retry using exponential backoff.

        Args:
            event (PaymentEvent): The payment event containing attempt count.

        Returns:
            Optional[DunningAction]: RETRY action with scheduled time.
        """
        # If execution reaches here, the failure is recoverable. Calculate next retry.
        # Simple formula: (2 ^ attempts) * base_hours
        multiplier = 2 ** (event.attempt_count - 1)
        hours_to_add = self.base_hours * multiplier

        # Limit the maximum wait time
        max_hours = self.max_days * 24
        hours_to_add = min(hours_to_add, max_hours)

        next_retry = datetime.now(timezone.utc) + timedelta(hours=hours_to_add)
        
        if next_retry.weekday() == 6:
            next_retry += timedelta(days=1)
            reason_suffix = " (adjusted from Sunday to Monday)"
        else:
            reason_suffix = ""

        return DunningAction(
            action_type=ActionType.RETRY,
            scheduled_for=next_retry,
            reason=f"Scheduled exponentially (+{hours_to_add}h){reason_suffix}",
        )
