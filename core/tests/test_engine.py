import pytest
from unittest.mock import MagicMock
from core.engine import DunningEngine
from core.models import PaymentEvent, DunningAction, ActionType

def test_dunning_engine_returns_first_matching_rule():
    # Arrange
    event = PaymentEvent(event_id="e1", tenant_id="t1", error_code="err", attempt_count=1, amount=100.0)
    
    rule1 = MagicMock()
    rule1.evaluate.return_value = None
    
    rule2 = MagicMock()
    rule2.evaluate.return_value = DunningAction(action_type=ActionType.RETRY, reason="retry")
    
    rule3 = MagicMock()
    
    engine = DunningEngine(rules=[rule1, rule2, rule3])
    
    # Act
    decision = engine.process(event)
    
    # Assert
    assert decision.action_type == ActionType.RETRY
    assert decision.reason == "retry"
    rule1.evaluate.assert_called_once_with(event)
    rule2.evaluate.assert_called_once_with(event)
    rule3.evaluate.assert_not_called()

def test_dunning_engine_returns_fallback_if_no_rules_match():
    # Arrange
    event = PaymentEvent(event_id="e1", tenant_id="t1", error_code="err", attempt_count=1, amount=100.0)
    
    rule1 = MagicMock()
    rule1.evaluate.return_value = None
    
    engine = DunningEngine(rules=[rule1])
    
    # Act
    decision = engine.process(event)
    
    # Assert
    assert decision.action_type == ActionType.CANCEL
    assert "Fallback" in decision.reason
    rule1.evaluate.assert_called_once_with(event)
