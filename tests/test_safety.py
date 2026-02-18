"""Unit tests for the Safety Module."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.safety import SafetyModule
from src.config_manager import SafetyConfig
from src.models import ClassificationResult, MatchedRule


class TestSafetyModule(unittest.TestCase):
    """Test safety checks."""

    def _make_classification(self, confidence=0.90):
        return ClassificationResult(
            intent="meeting_request", priority="medium", confidence=confidence
        )

    def _make_rule(self, action="reply", auto_send=True):
        return MatchedRule(rule_name="Test", action=action, auto_send=auto_send)

    def test_dry_run_blocks_everything(self):
        safety = SafetyModule(
            SafetyConfig(dry_run=True, confidence_threshold=0.85, max_sends_per_hour=20)
        )
        decision = safety.evaluate(self._make_classification(0.99), self._make_rule())
        self.assertFalse(decision.can_execute)
        self.assertFalse(decision.can_auto_send)
        self.assertIn("dry_run_active", decision.reasons)

    def test_high_confidence_passes(self):
        safety = SafetyModule(
            SafetyConfig(
                dry_run=False, confidence_threshold=0.85, max_sends_per_hour=20
            )
        )
        decision = safety.evaluate(self._make_classification(0.93), self._make_rule())
        self.assertTrue(decision.can_execute)
        self.assertTrue(decision.can_auto_send)

    def test_low_confidence_blocks(self):
        safety = SafetyModule(
            SafetyConfig(
                dry_run=False, confidence_threshold=0.85, max_sends_per_hour=20
            )
        )
        decision = safety.evaluate(self._make_classification(0.60), self._make_rule())
        self.assertFalse(decision.can_execute)
        self.assertIn("confidence_too_low", decision.reasons)

    def test_exact_threshold_passes(self):
        safety = SafetyModule(
            SafetyConfig(
                dry_run=False, confidence_threshold=0.85, max_sends_per_hour=20
            )
        )
        decision = safety.evaluate(self._make_classification(0.85), self._make_rule())
        self.assertTrue(decision.can_execute)

    def test_rate_limit_blocks_after_max(self):
        safety = SafetyModule(
            SafetyConfig(dry_run=False, confidence_threshold=0.50, max_sends_per_hour=3)
        )
        rule = self._make_rule()
        for _ in range(3):
            safety.evaluate(self._make_classification(0.95), rule)
            safety.record_send()
        decision = safety.evaluate(self._make_classification(0.95), rule)
        self.assertFalse(decision.can_execute)
        self.assertIn("rate_limit_exceeded", decision.reasons)

    def test_auto_send_false_blocks_sending(self):
        safety = SafetyModule(
            SafetyConfig(
                dry_run=False, confidence_threshold=0.85, max_sends_per_hour=20
            )
        )
        decision = safety.evaluate(
            self._make_classification(0.95), self._make_rule(auto_send=False)
        )
        self.assertTrue(decision.can_execute)
        self.assertFalse(decision.can_auto_send)  # Rule says no auto-send

    def test_safe_actions_bypass_rate_limit(self):
        safety = SafetyModule(
            SafetyConfig(dry_run=False, confidence_threshold=0.50, max_sends_per_hour=1)
        )
        safety.record_send()
        safety.record_send()  # Exhaust rate limit
        decision = safety.evaluate(
            self._make_classification(0.95), self._make_rule(action="ignore")
        )
        self.assertTrue(decision.can_execute)  # Ignore is always safe

    def test_zero_confidence_blocks(self):
        safety = SafetyModule(
            SafetyConfig(
                dry_run=False, confidence_threshold=0.85, max_sends_per_hour=20
            )
        )
        decision = safety.evaluate(self._make_classification(0.0), self._make_rule())
        self.assertFalse(decision.can_execute)

    def test_get_status(self):
        safety = SafetyModule(
            SafetyConfig(dry_run=True, confidence_threshold=0.85, max_sends_per_hour=20)
        )
        status = safety.get_status()
        self.assertTrue(status["dry_run"])
        self.assertEqual(status["confidence_threshold"], 0.85)
        self.assertEqual(status["sends_this_hour"], 0)


if __name__ == "__main__":
    unittest.main()
