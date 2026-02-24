# src/utils/cost_tracker.py

"""
R3: API Cost Tracker

Tracks Gemini API usage (tokens, costs) per call and in aggregate.
Persists data to a JSON file in the logs directory so costs survive restarts.

Gemini 2.5 Flash Pricing:
  - Input:  \$0.075 per 1M tokens
  - Output: \$0.30  per 1M tokens

Usage:
    tracker = CostTracker(log_dir="logs")
    tracker.record(
        operation="classify",
        model="gemini-2.5-flash",
        input_tokens=500,
        output_tokens=150,
    )
    summary = tracker.get_summary()
    print(summary.display_string())
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.models import CostRecord, CostSummary

logger = logging.getLogger(__name__)


class CostTracker:
    """
    R3: Tracks and persists Gemini API costs.

    Features:
      - Records token usage per API call
      - Calculates costs based on Gemini pricing
      - Maintains running session totals
      - Persists all-time totals to JSON file
      - Provides summary statistics and reporting

    Thread Safety:
      - Not thread-safe. If needed, wrap calls with a lock.
    """

    # Default pricing (Gemini 2.5 Flash)
    DEFAULT_INPUT_COST_PER_1M = 0.075
    DEFAULT_OUTPUT_COST_PER_1M = 0.30

    # Persistence file name
    COST_FILE = "api_costs.json"

    def __init__(
        self,
        log_dir: str = "logs",
        input_cost_per_1m: float = DEFAULT_INPUT_COST_PER_1M,
        output_cost_per_1m: float = DEFAULT_OUTPUT_COST_PER_1M,
    ):
        """
        Initialize the cost tracker.

        Args:
            log_dir: Directory to store the cost persistence file
            input_cost_per_1m: Cost per 1M input tokens
            output_cost_per_1m: Cost per 1M output tokens
        """
        self.log_dir = Path(log_dir)
        self.input_cost_per_1m = input_cost_per_1m
        self.output_cost_per_1m = output_cost_per_1m
        self.cost_file = self.log_dir / self.COST_FILE

        # ── All-time totals (loaded from file) ────
        self._total_calls: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_cost: float = 0.0
        self._cost_by_operation: dict[str, float] = {}
        self._records: list[dict] = []

        # ── Session totals (reset each startup) ───
        self._session_start: str = datetime.now().isoformat()
        self._session_calls: int = 0
        self._session_input_tokens: int = 0
        self._session_output_tokens: int = 0
        self._session_cost: float = 0.0

        # Load previous data
        self._ensure_log_dir()
        self._load()

        logger.info(
            f"[R3] CostTracker initialized | "
            f"log_dir={self.log_dir} | "
            f"previous_total_cost=${self._total_cost:.6f} | "
            f"previous_calls={self._total_calls}"
        )

    # ──────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────

    def record(
        self,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: Optional[int] = None,
        input_cost: Optional[float] = None,
        output_cost: Optional[float] = None,
        total_cost: Optional[float] = None,
        thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> CostRecord:
        """
        Record a single API call's cost.

        Can accept pre-calculated costs or calculate them from tokens.

        Args:
            operation: What the call was for ("classify", "reply_generation", etc.)
            model: Model name used
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens
            total_tokens: Total tokens (auto-calculated if not provided)
            input_cost: Pre-calculated input cost (auto-calculated if not provided)
            output_cost: Pre-calculated output cost (auto-calculated if not provided)
            total_cost: Pre-calculated total cost (auto-calculated if not provided)
            thread_id: Optional email thread ID
            metadata: Optional extra data

        Returns:
            The CostRecord that was created
        """
        # Calculate costs if not provided
        if input_cost is None:
            input_cost = (input_tokens / 1_000_000) * self.input_cost_per_1m
        if output_cost is None:
            output_cost = (output_tokens / 1_000_000) * self.output_cost_per_1m
        if total_cost is None:
            total_cost = input_cost + output_cost
        if total_tokens is None:
            total_tokens = input_tokens + output_tokens

        # Create the record
        cost_record = CostRecord(
            timestamp=datetime.now().isoformat(),
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            thread_id=thread_id,
            metadata=metadata,
        )

        # Update all-time totals
        self._total_calls += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost += total_cost
        self._cost_by_operation[operation] = (
            self._cost_by_operation.get(operation, 0.0) + total_cost
        )

        # Update session totals
        self._session_calls += 1
        self._session_input_tokens += input_tokens
        self._session_output_tokens += output_tokens
        self._session_cost += total_cost

        # Store record
        self._records.append(cost_record.to_dict())

        # Persist to file
        self._save()

        # R9: Log the cost
        logger.info(
            f"[R3] Cost recorded | op={operation} "
            f"in={input_tokens} out={output_tokens} "
            f"cost=${total_cost:.6f} "
            f"session_total=${self._session_cost:.6f}"
        )

        return cost_record

    def get_summary(self) -> CostSummary:
        """
        R3: Get aggregated cost statistics.

        Returns:
            CostSummary with all-time and session totals
        """
        total_tokens = self._total_input_tokens + self._total_output_tokens
        avg_cost = (
            self._total_cost / self._total_calls if self._total_calls > 0 else 0.0
        )
        avg_tokens = total_tokens / self._total_calls if self._total_calls > 0 else 0.0

        return CostSummary(
            total_calls=self._total_calls,
            total_input_tokens=self._total_input_tokens,
            total_output_tokens=self._total_output_tokens,
            total_tokens=total_tokens,
            total_cost=self._total_cost,
            session_calls=self._session_calls,
            session_cost=self._session_cost,
            cost_by_operation=dict(self._cost_by_operation),
            avg_cost_per_call=avg_cost,
            avg_tokens_per_call=avg_tokens,
        )

    def get_session_cost(self) -> float:
        """Get total cost for the current session."""
        return self._session_cost

    def get_total_cost(self) -> float:
        """Get all-time total cost."""
        return self._total_cost

    def get_stats(self) -> dict:
        """
        R3 (AC8): Retrieve cost statistics as a dict.
        Matches the acceptance criteria:
        total_calls, total_input_tokens, total_output_tokens, total_cost
        """
        return {
            "total_calls": self._total_calls,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_cost": self._total_cost,
            "session_calls": self._session_calls,
            "session_cost": self._session_cost,
        }

    def get_recent_records(self, n: int = 10) -> list[dict]:
        """Get the N most recent cost records."""
        return self._records[-n:]

    def display_costs(self) -> str:
        """
        R3 (AC7): Get formatted cost display for console output.
        Shows current session costs and total accumulated costs.
        """
        summary = self.get_summary()
        return summary.display_string()

    # ──────────────────────────────────────────────
    # PERSISTENCE
    # ──────────────────────────────────────────────

    def _ensure_log_dir(self):
        """Create the log directory if it doesn't exist."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"[R3] Could not create log directory {self.log_dir}: {e}")

    def _load(self):
        """
        R3 (AC6): Load previous cost data from the persistence file.
        Called at startup to resume tracking from where we left off.
        """
        if not self.cost_file.exists():
            logger.debug(f"[R3] No previous cost file found at {self.cost_file}")
            return

        try:
            with open(self.cost_file, "r") as f:
                data = json.load(f)

            self._total_calls = data.get("total_calls", 0)
            self._total_input_tokens = data.get("total_input_tokens", 0)
            self._total_output_tokens = data.get("total_output_tokens", 0)
            self._total_cost = data.get("total_cost", 0.0)
            self._cost_by_operation = data.get("cost_by_operation", {})
            self._records = data.get("records", [])

            logger.info(
                f"[R3] Loaded previous cost data: "
                f"{self._total_calls} calls, "
                f"${self._total_cost:.6f} total cost"
            )

        except json.JSONDecodeError as e:
            logger.warning(f"[R3] Cost file corrupted, starting fresh: {e}")
            self._reset_totals()

        except Exception as e:
            # R8: Persistence failure should not crash the agent
            logger.warning(
                f"[R8] Failed to load cost data: {e}. Starting with fresh counters."
            )
            self._reset_totals()

    def _save(self):
        """
        R3 (AC5): Persist cost data to JSON file in the logs directory.
        Called after every record() to ensure data survives crashes.
        """
        data = {
            "last_updated": datetime.now().isoformat(),
            "total_calls": self._total_calls,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_cost": self._total_cost,
            "cost_by_operation": self._cost_by_operation,
            "records": self._records[
                -500:
            ],  # Keep last 500 records to avoid huge files
        }

        try:
            # Write to temp file first, then rename (atomic write)
            temp_file = self.cost_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            temp_file.replace(self.cost_file)

            logger.debug(f"[R3] Cost data saved to {self.cost_file}")

        except Exception as e:
            # R8 (AC3): File write failure should not crash the agent
            logger.warning(
                f"[R8] Failed to save cost data: {e}. In-memory tracking continues."
            )

    def _reset_totals(self):
        """Reset all-time totals (used when persistence file is corrupted)."""
        self._total_calls = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        self._cost_by_operation = {}
        self._records = []

    # ──────────────────────────────────────────────
    # RESET / ADMIN
    # ──────────────────────────────────────────────

    def reset_session(self):
        """Reset session counters (e.g., between processing runs)."""
        self._session_calls = 0
        self._session_input_tokens = 0
        self._session_output_tokens = 0
        self._session_cost = 0.0
        self._session_start = datetime.now().isoformat()
        logger.info("[R3] Session counters reset")

    def reset_all(self):
        """Reset ALL counters and delete the persistence file."""
        self._reset_totals()
        self._session_calls = 0
        self._session_input_tokens = 0
        self._session_output_tokens = 0
        self._session_cost = 0.0

        try:
            if self.cost_file.exists():
                self.cost_file.unlink()
                logger.info(f"[R3] Cost file deleted: {self.cost_file}")
        except Exception as e:
            logger.warning(f"[R3] Could not delete cost file: {e}")

        logger.info("[R3] All cost data reset")
