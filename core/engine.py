from typing import List
from core.models import PaymentEvent, DunningAction, ActionType
from core.rules import DunningRule

class DunningEngine:
    """Evalúa un evento de pago contra una cadena de reglas inyectadas."""
    
    def __init__(self, rules: List[DunningRule]):
        self.rules = rules

    def process(self, event: PaymentEvent) -> DunningAction:
        for rule in self.rules:
            decision = rule.evaluate(event)
            if decision is not None:
                return decision
        
        return DunningAction(
            action_type=ActionType.CANCEL, 
            reason="Fallback: No rule matched the event."
        )