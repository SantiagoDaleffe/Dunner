import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from core.rules import HardDeclineRule, MaxAttemptsRule, HighValueAlertRule, ExponentialBackoffRule
from core.models import PaymentEvent, ActionType

def test_hard_decline_rule():
    rule = HardDeclineRule(fatal_errors=["fraud", "stolen"])
    event = PaymentEvent(event_id="e1", tenant_id="t1", error_code="fraud", attempt_count=1, amount=100.0)
    
    action = rule.evaluate(event)
    assert action is not None
    assert action.action_type == ActionType.CANCEL
    assert "fatal" in action.reason.lower()

    event.error_code = "temp_issue"
    assert rule.evaluate(event) is None

def test_max_attempts_rule():
    rule = MaxAttemptsRule(max_attempts=3)
    event = PaymentEvent(event_id="e1", tenant_id="t1", error_code="err", attempt_count=3, amount=100.0)
    
    action = rule.evaluate(event)
    assert action is not None
    assert action.action_type == ActionType.CANCEL
    assert "max attempts" in action.reason.lower()

    event.attempt_count = 2
    assert rule.evaluate(event) is None

def test_high_value_alert_rule():
    rule = HighValueAlertRule(threshold_amount=1000.0)
    event = PaymentEvent(event_id="e1", tenant_id="t1", error_code="err", attempt_count=1, amount=1500.0, currency="USD")
    
    action = rule.evaluate(event)
    assert action is not None
    assert action.action_type == ActionType.ALERT
    
    event.amount = 500.0
    assert rule.evaluate(event) is None

@patch("core.rules.datetime")
def test_exponential_backoff_rule(mock_datetime):
    fixed_now = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = fixed_now
    
    rule = ExponentialBackoffRule(base_hours=24)
    event = PaymentEvent(event_id="e1", tenant_id="t1", error_code="err", attempt_count=1, amount=100.0)
    
    action = rule.evaluate(event)
    assert action is not None
    assert action.action_type == ActionType.RETRY
    # 24 * 2^(1-1) = 24 hours
    assert action.scheduled_for == fixed_now + timedelta(hours=24)
    
    event.attempt_count = 2
    action = rule.evaluate(event)
    # 24 * 2^(2-1) = 48 hours
    assert action.scheduled_for == fixed_now + timedelta(hours=48)
