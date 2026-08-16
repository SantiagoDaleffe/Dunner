from typing import List
from core.models import PaymentEvent, DunningAction, ActionType
from core.rules import DunningRule


class DunningEngine:
    """Evaluates payment events against configured dunning rules.

    The engine iterates through the registered rules in order and returns the
    first non-None decision. If no rule matches, it falls back to a cancellation
    action with a descriptive reason.
    """

    def __init__(self, rules: List[DunningRule]):
        self.rules = rules

    def process(self, event: PaymentEvent) -> DunningAction:
        for rule in self.rules:
            decision = rule.evaluate(event)
            if decision is not None:
                return decision

        return DunningAction(
            action_type=ActionType.CANCEL, reason="Fallback: No rule matched the event."
        )
