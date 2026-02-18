# src/rule_engine.py

"""
Rule Engine
Matches email classifications against user-defined rules.
Pure logic module — no side effects, no API calls, no I/O.

Rules are defined in config.yaml and processed in order.
First matching rule wins.
"""

import logging
from typing import Optional

from src.models import EmailData, ClassificationResult, MatchedRule
from src.config_manager import RuleConfig


logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Evaluates classification results against configured rules.
    
    Rules are processed in ORDER (first match wins).
    All conditions within a rule must match (AND logic).
    
    Usage:
        engine = RuleEngine(config.rules)
        matched = engine.match(email_data, classification)
        if matched:
            print(f"Rule: {matched.rule_name}, Action: {matched.action}")
    """

    def __init__(self, rules: list):
        """
        Args:
            rules: List of RuleConfig objects from configuration
        """
        self.rules = rules
        logger.debug(f"Rule engine initialized with {len(rules)} rules")

    def match(
        self,
        email_data: EmailData,
        classification: ClassificationResult,
    ) -> Optional[MatchedRule]:
        """
        Find the first rule that matches the given classification.
        
        Args:
            email_data: The original email (for sender/subject matching)
            classification: AI classification result
            
        Returns:
            MatchedRule if a rule matches, None otherwise
        """
        for rule in self.rules:
            is_match, matched_conditions = self._evaluate_rule(
                rule, email_data, classification
            )

            if is_match:
                logger.info(f"Rule matched: '{rule.name}' -> action: {rule.action}")

                return MatchedRule(
                    rule_name=rule.name,
                    action=rule.action,
                    auto_send=rule.auto_send,
                    template=rule.template,
                    conditions_matched=matched_conditions,
                )

        logger.info("No rules matched for this classification")
        return None

    def _evaluate_rule(
        self,
        rule: RuleConfig,
        email_data: EmailData,
        classification: ClassificationResult,
    ) -> tuple:
        """
        Evaluate whether a single rule matches.
        ALL conditions must be true (AND logic).
        
        Args:
            rule: The rule to evaluate
            email_data: Original email
            classification: AI classification
            
        Returns:
            Tuple of (is_match: bool, matched_conditions: dict)
        """
        matched_conditions = {}
        conditions = rule.conditions

        # ── Check intent ──
        if "intent" in conditions:
            expected = conditions["intent"]
            actual = classification.intent

            if actual != expected:
                return False, {}

            matched_conditions["intent"] = f"{actual} == {expected}"

        # ── Check priority ──
        if "priority" in conditions:
            expected = conditions["priority"]
            actual = classification.priority

            if actual != expected:
                return False, {}

            matched_conditions["priority"] = f"{actual} == {expected}"

        # ── Check minimum confidence ──
        if "confidence_min" in conditions:
            minimum = float(conditions["confidence_min"])
            actual = classification.confidence

            if actual < minimum:
                return False, {}

            matched_conditions["confidence_min"] = f"{actual:.2f} >= {minimum:.2f}"

        # ── Check sender contains ──
        if "sender_contains" in conditions:
            pattern = conditions["sender_contains"].lower()
            actual = email_data.from_address.lower()

            if pattern not in actual:
                return False, {}

            matched_conditions["sender_contains"] = f"'{pattern}' found in '{actual}'"

        # ── Check subject contains ──
        if "subject_contains" in conditions:
            keyword = conditions["subject_contains"].lower()
            actual = email_data.subject.lower()

            if keyword not in actual:
                return False, {}

            matched_conditions["subject_contains"] = f"'{keyword}' found in '{actual}'"

        # All conditions passed
        return True, matched_conditions

    def get_rules_summary(self) -> list:
        """
        Get a summary of all configured rules.
        Useful for display/logging at startup.
        
        Returns:
            List of dicts with rule summaries
        """
        summary = []
        for i, rule in enumerate(self.rules, 1):
            summary.append({
                "order": i,
                "name": rule.name,
                "conditions": rule.conditions,
                "action": rule.action,
                "auto_send": rule.auto_send,
            })
        return summary