"""Unit tests for the Rule Engine."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.core.rule_engine import RuleEngine
from src.utils.config_manager import RuleConfig
from src.core.models import EmailData, ClassificationResult


class TestRuleEngine(unittest.TestCase):
    """Test rule matching logic."""

    def setUp(self):
        """Create test rules and engine."""
        self.rules = [
            RuleConfig(name="Spam", conditions={"intent": "spam"}, action="ignore"),
            RuleConfig(
                name="Newsletter",
                conditions={"intent": "newsletter", "confidence_min": 0.80},
                action="archive",
            ),
            RuleConfig(
                name="Urgent",
                conditions={"intent": "urgent_issue", "priority": "high"},
                action="flag_and_draft",
            ),
            RuleConfig(
                name="Meeting",
                conditions={"intent": "meeting_request"},
                action="reply",
                auto_send=True,
            ),
            RuleConfig(
                name="VIP",
                conditions={"intent": "general_inquiry", "sender_contains": "@vip.com"},
                action="flag",
            ),
            RuleConfig(
                name="General",
                conditions={"intent": "general_inquiry", "confidence_min": 0.85},
                action="reply",
                auto_send=True,
            ),
        ]
        self.engine = RuleEngine(self.rules)

    def _make_email(self, from_addr="test@example.com", subject="Test"):
        return EmailData(
            id="1",
            from_address=from_addr,
            to_address="agent@gmail.com",
            subject=subject,
            body="Test body",
            date="2025-06-14",
        )

    def _make_classification(
        self, intent="general_inquiry", priority="medium", confidence=0.90
    ):
        return ClassificationResult(
            intent=intent, priority=priority, confidence=confidence
        )

    def test_spam_matches(self):
        result = self.engine.match(
            self._make_email(), self._make_classification("spam", "low", 0.98)
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_name, "Spam")
        self.assertEqual(result.action, "ignore")

    def test_newsletter_high_confidence_matches(self):
        result = self.engine.match(
            self._make_email(), self._make_classification("newsletter", "low", 0.95)
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_name, "Newsletter")

    def test_newsletter_low_confidence_no_match(self):
        result = self.engine.match(
            self._make_email(), self._make_classification("newsletter", "low", 0.50)
        )
        self.assertIsNone(result)  # Below confidence_min 0.80

    def test_urgent_high_priority_matches(self):
        result = self.engine.match(
            self._make_email(), self._make_classification("urgent_issue", "high", 0.96)
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_name, "Urgent")

    def test_urgent_medium_priority_no_match(self):
        result = self.engine.match(
            self._make_email(),
            self._make_classification("urgent_issue", "medium", 0.96),
        )
        self.assertIsNone(result)  # Priority doesn't match

    def test_meeting_matches_with_auto_send(self):
        result = self.engine.match(
            self._make_email(),
            self._make_classification("meeting_request", "medium", 0.93),
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_name, "Meeting")
        self.assertTrue(result.auto_send)

    def test_vip_sender_matches_before_general(self):
        result = self.engine.match(
            self._make_email("ceo@vip.com"),
            self._make_classification("general_inquiry", "medium", 0.90),
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_name, "VIP")  # VIP rule comes before General

    def test_no_match_for_unknown_intent(self):
        result = self.engine.match(
            self._make_email(), self._make_classification("follow_up", "medium", 0.90)
        )
        self.assertIsNone(result)

    def test_first_match_wins(self):
        """Spam rule should match before any other rule."""
        result = self.engine.match(
            self._make_email(), self._make_classification("spam", "high", 0.99)
        )
        self.assertEqual(result.rule_name, "Spam")

    def test_subject_contains(self):
        rules = [
            RuleConfig(
                name="Urgent Subject",
                conditions={"subject_contains": "urgent"},
                action="flag",
            )
        ]
        engine = RuleEngine(rules)
        result = engine.match(
            self._make_email(subject="URGENT: Help needed"), self._make_classification()
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_name, "Urgent Subject")


if __name__ == "__main__":
    unittest.main()
