# src/safety.py

"""
Safety Module
Prevents the agent from taking harmful or unintended actions.

Three safety gates:
  1. Confidence threshold — Is the AI sure enough?
  2. Rate limiting — Have we sent too many emails?
  3. Dry-run mode — Are we in testing mode?

Safe by default: blocks everything unless explicitly allowed.
"""

import time
import logging
from collections import deque
from typing import Optional

from src.models import ClassificationResult, MatchedRule, SafetyDecision
from src.config_manager import SafetyConfig


logger = logging.getLogger(__name__)


class SafetyModule:
    """
    Evaluates whether an action is safe to execute.
    
    Usage:
        safety = SafetyModule(config.safety)
        decision = safety.evaluate(classification, matched_rule)
        if decision.can_execute:
            # proceed with action
        else:
            # log and skip
    """

    # Actions that are always safe (they don't send emails or modify anything critical)
    SAFE_ACTIONS = {"ignore", "flag", "flag_and_draft"}

    # Actions that involve sending an email (need full safety checks)
    SEND_ACTIONS = {"reply", "draft_reply", "auto_reply"}

    def __init__(self, config: SafetyConfig):
        self.config = config
        self.dry_run = config.dry_run

        # Rate limiting: track timestamps of sent emails
        self._send_timestamps = deque()

        logger.debug(
            f"Safety module initialized: "
            f"dry_run={self.dry_run}, "
            f"threshold={config.confidence_threshold}, "
            f"max_sends={config.max_sends_per_hour}/hr"
        )

    # ──────────────────────────────────────────────
    # MAIN EVALUATION METHOD
    # ──────────────────────────────────────────────

    def evaluate(
        self,
        classification: ClassificationResult,
        matched_rule: Optional[MatchedRule] = None,
    ) -> SafetyDecision:
        """
        Run all safety checks and return a decision.
        
        Args:
            classification: AI classification result
            matched_rule: The rule that matched (if any)
            
        Returns:
            SafetyDecision with can_execute, can_auto_send, and reasons
        """
        reasons = []
        warnings = []

        # ── Gate 1: Dry Run Mode ──
        is_dry_run = self._check_dry_run()
        if is_dry_run:
            reasons.append("dry_run_active")

        # ── Gate 2: Confidence Check ──
        confidence_ok = self._check_confidence(classification.confidence)
        if confidence_ok:
            reasons.append("confidence_ok")
        else:
            reasons.append("confidence_too_low")

        # ── Gate 3: Rate Limit Check ──
        rate_limit_ok = self._check_rate_limit()
        if rate_limit_ok:
            reasons.append("rate_limit_ok")
        else:
            reasons.append("rate_limit_exceeded")

        # ── Check if approaching rate limit ──
        sends_this_hour = self._get_sends_this_hour()
        if sends_this_hour >= self.config.max_sends_per_hour * 0.8:
            warnings.append(
                f"approaching_rate_limit ({sends_this_hour}/{self.config.max_sends_per_hour})"
            )

        # ── Determine action safety ──
        action = matched_rule.action if matched_rule else "none"
        is_safe_action = action in self.SAFE_ACTIONS

        # ── Calculate final decisions ──

        # can_execute: Can we take the action at all?
        if is_dry_run:
            can_execute = False
        elif is_safe_action:
            # Safe actions (ignore, flag) only need confidence check
            can_execute = confidence_ok
        else:
            # All other actions need all checks to pass
            can_execute = confidence_ok and rate_limit_ok

        # can_auto_send: Can we send an email without human review?
        auto_send_requested = matched_rule.auto_send if matched_rule else False
        can_auto_send = (
            can_execute
            and auto_send_requested
            and not is_dry_run
            and confidence_ok
            and rate_limit_ok
        )

        decision = SafetyDecision(
            can_execute=can_execute,
            can_auto_send=can_auto_send,
            reasons=reasons,
            warnings=warnings,
        )

        # Log the decision
        self._log_decision(classification, matched_rule, decision)

        return decision

    # ──────────────────────────────────────────────
    # INDIVIDUAL SAFETY CHECKS
    # ──────────────────────────────────────────────

    def _check_dry_run(self) -> bool:
        """Check if dry-run mode is active."""
        return self.dry_run

    def _check_confidence(self, confidence: float) -> bool:
        """
        Check if confidence meets the threshold.
        
        Args:
            confidence: AI confidence score (0.0 to 1.0)
            
        Returns:
            True if confidence is high enough
        """
        return confidence >= self.config.confidence_threshold

    def _check_rate_limit(self) -> bool:
        """
        Check if we're within the rate limit.
        
        Returns:
            True if we haven't exceeded the hourly limit
        """
        self._clean_old_timestamps()
        return len(self._send_timestamps) < self.config.max_sends_per_hour

    # ──────────────────────────────────────────────
    # RATE LIMIT TRACKING
    # ──────────────────────────────────────────────

    def record_send(self):
        """
        Record that an email was sent.
        Call this AFTER successfully sending an email.
        """
        self._send_timestamps.append(time.time())
        sends = len(self._send_timestamps)
        logger.debug(
            f"Send recorded. "
            f"Total this hour: {sends}/{self.config.max_sends_per_hour}"
        )

    def _clean_old_timestamps(self):
        """Remove timestamps older than 1 hour."""
        one_hour_ago = time.time() - 3600
        while self._send_timestamps and self._send_timestamps[0] < one_hour_ago:
            self._send_timestamps.popleft()

    def _get_sends_this_hour(self) -> int:
        """Get the number of emails sent in the last hour."""
        self._clean_old_timestamps()
        return len(self._send_timestamps)

    # ──────────────────────────────────────────────
    # LOGGING
    # ──────────────────────────────────────────────

    def _log_decision(
        self,
        classification: ClassificationResult,
        matched_rule: Optional[MatchedRule],
        decision: SafetyDecision,
    ):
        """Log the safety decision for audit trail."""
        rule_name = matched_rule.rule_name if matched_rule else "none"
        action = matched_rule.action if matched_rule else "none"

        logger.info(
            f"Safety decision: "
            f"rule='{rule_name}', "
            f"action='{action}', "
            f"confidence={classification.confidence:.2f}, "
            f"can_execute={decision.can_execute}, "
            f"can_auto_send={decision.can_auto_send}, "
            f"reasons={decision.reasons}"
        )

        if decision.warnings:
            for warning in decision.warnings:
                logger.warning(f"Safety warning: {warning}")

    # ──────────────────────────────────────────────
    # STATUS
    # ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Get current safety module status.
        Useful for display/monitoring.
        """
        return {
            "dry_run": self.dry_run,
            "confidence_threshold": self.config.confidence_threshold,
            "max_sends_per_hour": self.config.max_sends_per_hour,
            "sends_this_hour": self._get_sends_this_hour(),
            "rate_limit_remaining": max(
                0, self.config.max_sends_per_hour - self._get_sends_this_hour()
            ),
        }