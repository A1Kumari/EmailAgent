# src/audit_logger.py

"""
Audit Logger
Records every processing decision as structured JSON.
Provides a complete audit trail for accountability and debugging.

Console logging is handled by display.py.
This module handles FILE-BASED structured logging.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

from src.models import ProcessingResult
from src.config_manager import LoggingConfig


logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Logs all email processing results to structured JSON files.
    
    Each run creates entries in a daily log file.
    Format: logs/audit_YYYY-MM-DD.json (one JSON object per line)
    
    Usage:
        audit = AuditLogger(config.logging)
        audit.log_result(processing_result)
        audit.log_summary(all_results)
    """

    def __init__(self, config: LoggingConfig):
        self.log_dir = config.log_dir
        self._ensure_log_dir()

        # Set up Python's logging module for general logging
        self._setup_file_logging(config)

    def _ensure_log_dir(self):
        """Create log directory if it doesn't exist."""
        os.makedirs(self.log_dir, exist_ok=True)

    def _setup_file_logging(self, config: LoggingConfig):
        """Setup Python logging to write to file."""
        log_file = os.path.join(
            self.log_dir,
            f"agent_{datetime.now().strftime('%Y-%m-%d')}.log"
        )

        # File handler for detailed logs
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, config.file_level.upper(), logging.DEBUG))
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
        ))

        # Add to root logger
        root_logger = logging.getLogger()
        # Avoid adding duplicate handlers
        if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
            root_logger.addHandler(file_handler)

    # ──────────────────────────────────────────────
    # AUDIT TRAIL (Structured JSON)
    # ──────────────────────────────────────────────

    def log_result(self, result: ProcessingResult):
        """
        Log a single processing result as structured JSON.
        Appends one JSON line to the daily audit file.
        """
        audit_file = os.path.join(
            self.log_dir,
            f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        )

        record = self._build_audit_record(result)

        try:
            with open(audit_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def _build_audit_record(self, result: ProcessingResult) -> dict:
        """Build a structured audit record from a ProcessingResult."""
        record = {
            "timestamp": result.timestamp,
            "email": {
                "id": result.email.id,
                "from": result.email.from_address,
                "subject": result.email.subject,
                "date": result.email.date,
            },
            "action_taken": result.action_taken,
            "success": result.success,
        }

        # Add classification if available
        if result.classification:
            record["classification"] = {
                "intent": result.classification.intent,
                "priority": result.classification.priority,
                "confidence": result.classification.confidence,
                "entities": result.classification.entities,
                "reasoning": result.classification.reasoning,
            }

        # Add rule match if available
        if result.matched_rule:
            record["rule_matched"] = {
                "name": result.matched_rule.rule_name,
                "action": result.matched_rule.action,
                "auto_send": result.matched_rule.auto_send,
                "conditions_matched": result.matched_rule.conditions_matched,
            }

        # Add safety decision if available
        if result.safety_decision:
            record["safety"] = {
                "can_execute": result.safety_decision.can_execute,
                "can_auto_send": result.safety_decision.can_auto_send,
                "reasons": result.safety_decision.reasons,
                "warnings": result.safety_decision.warnings,
            }

        # Add reply if generated
        if result.reply_generated:
            record["reply_generated"] = result.reply_generated[:500]  # Truncate for log

        # Add error if any
        if result.error_message:
            record["error"] = result.error_message

        return record

    # ──────────────────────────────────────────────
    # RUN SUMMARY
    # ──────────────────────────────────────────────

    def log_summary(self, results: list, dry_run: bool):
        """Log a summary of the entire run."""
        audit_file = os.path.join(
            self.log_dir,
            f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        )

        # Count actions
        action_counts = {}
        errors = 0
        for result in results:
            action = result.action_taken
            action_counts[action] = action_counts.get(action, 0) + 1
            if not result.success:
                errors += 1

        summary = {
            "timestamp": datetime.now().isoformat(),
            "type": "run_summary",
            "dry_run": dry_run,
            "total_processed": len(results),
            "action_counts": action_counts,
            "errors": errors,
        }

        try:
            with open(audit_file, "a") as f:
                f.write(json.dumps(summary) + "\n")
        except Exception as e:
            logger.error(f"Failed to write summary log: {e}")

        logger.info(
            f"Run summary: {len(results)} processed, "
            f"{errors} errors, dry_run={dry_run}"
        )