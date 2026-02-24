# src/core/models.py

"""
Data models used across all modules.
These define the SHAPE of data flowing through the system.
No business logic here — just data structures.

Enhanced with:
  - R2: Thread context support
  - R3: Cost tracking models (CostRecord, CostSummary)
  - R4: Function calling models (ActionSuggestion)
  - R7: Feature flag model (FeatureFlags)
  - R6: Full backward compatibility — no existing fields removed or renamed
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


# ──────────────────────────────────────────────
# EMAIL DATA
# ──────────────────────────────────────────────


@dataclass
class EmailData:
    """
    Represents a single email fetched from Gmail.
    Created by: GmailClient
    Used by: GeminiAgent, Main orchestrator
    """

    id: str  # IMAP message ID
    from_address: str  # "John Doe <john@company.com>"
    to_address: str  # "agent@gmail.com"
    subject: str  # Email subject line
    body: str  # Plain text body content
    date: str  # When email was received
    message_id: Optional[str] = None  # Unique email ID (for threading)
    in_reply_to: Optional[str] = None  # Message-ID this replies to
    references: Optional[str] = None  # Full thread reference chain
    thread_messages: list = field(default_factory=list)  # Previous messages in thread

    # ── R2: Thread context helpers ────────────────

    @property
    def is_part_of_thread(self) -> bool:
        """R2: Check if this email belongs to a conversation thread."""
        return bool(
            self.in_reply_to or self.references or len(self.thread_messages) > 0
        )

    @property
    def thread_depth(self) -> int:
        """R2: How many previous messages exist in this thread."""
        return len(self.thread_messages)

    @property
    def thread_participants(self) -> list[str]:
        """R2: Extract unique senders from thread messages."""
        participants = set()
        participants.add(self.from_address)
        for msg in self.thread_messages:
            sender = msg.get("from", "")
            if sender:
                participants.add(sender)
        return sorted(participants)

    @property
    def reference_chain(self) -> list[str]:
        """R2: Parse References header into list of message IDs."""
        if not self.references:
            return []
        return [ref.strip() for ref in self.references.split() if ref.strip()]


# ──────────────────────────────────────────────
# CLASSIFICATION RESULT
# ──────────────────────────────────────────────


@dataclass
class ClassificationResult:
    """
    AI classification of an email.
    Created by: GeminiAgent
    Used by: RuleEngine, SafetyModule, Main orchestrator

    Intent categories:
      - meeting_request: Someone wants to schedule a meeting
      - newsletter: Promotional / marketing / subscription email
      - urgent_issue: Time-sensitive problem needing immediate attention
      - spam: Junk / phishing / scam email
      - general_inquiry: General question or conversation
      - follow_up: Continuation of an existing thread
      - complaint: Negative feedback or issue report
      - action_required: Task or request that needs a response
    """

    intent: str  # Category of the email
    priority: str  # "high" / "medium" / "low"
    confidence: float  # 0.0 to 1.0 — how sure the AI is
    entities: dict = field(
        default_factory=lambda: {"dates": [], "names": [], "action_items": []}
    )
    suggested_action: str = "none"  # What AI recommends doing
    reasoning: str = ""  # Why AI classified this way

    # ── R4: Function calling suggestion ───────────
    # This is populated by GeminiAgent when function calling is enabled.
    # It is OPTIONAL — None when function calling is off or fails.
    function_call_suggestion: Optional[dict] = field(default=None)

    # ── R1: Track which classification path was used ──
    classification_method: str = "legacy"  # "json_mode" or "legacy"

    # ── R2: Whether thread context was used ───────
    thread_context_used: bool = False
    thread_depth_used: int = 0

    # ── Helpers ───────────────────────────────────

    @property
    def is_high_confidence(self) -> bool:
        """Check if classification confidence is above typical threshold."""
        return self.confidence >= 0.8

    @property
    def has_function_suggestion(self) -> bool:
        """R4: Check if a function call suggestion is attached."""
        return self.function_call_suggestion is not None

    @property
    def effective_action(self) -> str:
        """
        R4: Get the best action to take, considering both
        classification and function call suggestion.

        Priority: suggested_action from classification takes precedence
        (preserves first-match-wins rule engine behavior).
        Function call suggestion is a secondary signal.
        """
        if self.suggested_action and self.suggested_action != "none":
            return self.suggested_action
        if self.function_call_suggestion:
            return self.function_call_suggestion.get("action_type", "none")
        return "none"

    def to_dict(self) -> dict:
        """Serialize to dictionary for logging/persistence."""
        result = {
            "intent": self.intent,
            "priority": self.priority,
            "confidence": self.confidence,
            "entities": self.entities,
            "suggested_action": self.suggested_action,
            "reasoning": self.reasoning,
            "classification_method": self.classification_method,
            "thread_context_used": self.thread_context_used,
            "thread_depth_used": self.thread_depth_used,
        }
        if self.function_call_suggestion:
            result["function_call_suggestion"] = self.function_call_suggestion
        return result


# ──────────────────────────────────────────────
# R4: ACTION SUGGESTION (from Function Calling)
# ──────────────────────────────────────────────


@dataclass
class ActionSuggestion:
    """
    R4: Structured action suggestion from Gemini function calling.
    Created by: GeminiAgent._get_function_call_suggestion()
    Used by: RuleEngine (as secondary signal), Main orchestrator

    This is the typed version of what function calling returns.
    The raw dict is stored on ClassificationResult.function_call_suggestion,
    but this model can be used when you want validation.
    """

    action_type: str  # "reply" / "draft_reply" / "archive" / "flag" / "ignore" / "flag_and_draft"
    confidence: float  # 0.0 to 1.0
    reasoning: str  # Why this action was suggested
    reply_template_hint: str = ""  # Tone/content guidance for replies

    # Valid action types
    VALID_ACTIONS = {
        "reply",
        "draft_reply",
        "archive",
        "flag",
        "ignore",
        "flag_and_draft",
    }

    def __post_init__(self):
        """Validate fields after creation."""
        # Clamp confidence
        self.confidence = max(0.0, min(1.0, self.confidence))

        # Validate action type
        if self.action_type not in self.VALID_ACTIONS:
            raise ValueError(
                f"Invalid action_type '{self.action_type}'. "
                f"Must be one of: {self.VALID_ACTIONS}"
            )

    @classmethod
    def from_dict(cls, data: dict) -> "ActionSuggestion":
        """
        Create from a raw dict (e.g., from function calling response).
        Handles missing fields gracefully.
        """
        return cls(
            action_type=data.get("action_type", "ignore"),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", ""),
            reply_template_hint=data.get("reply_template_hint", ""),
        )

    @classmethod
    def safe_from_dict(cls, data: dict) -> Optional["ActionSuggestion"]:
        """
        Create from dict with full error handling.
        Returns None instead of raising on invalid data.
        """
        try:
            return cls.from_dict(data)
        except (ValueError, TypeError, KeyError):
            return None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "action_type": self.action_type,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "reply_template_hint": self.reply_template_hint,
        }


# ──────────────────────────────────────────────
# R3: COST TRACKING MODELS
# ──────────────────────────────────────────────


@dataclass
class CostRecord:
    """
    R3: Records cost data for a single Gemini API call.
    Created by: CostTracker
    Used by: CostTracker (persistence), Main orchestrator (display)
    """

    timestamp: str  # ISO format timestamp
    operation: str  # "classify" / "reply_generation" / "function_call" / etc.
    model: str  # "gemini-2.5-flash" etc.
    input_tokens: int = 0  # Prompt tokens
    output_tokens: int = 0  # Completion tokens
    total_tokens: int = 0  # input + output
    input_cost: float = 0.0  # $ for input tokens
    output_cost: float = 0.0  # $ for output tokens
    total_cost: float = 0.0  # $ total for this call
    thread_id: Optional[str] = None  # Associated email thread if any
    metadata: Optional[dict] = field(default=None)  # Extra info

    @classmethod
    def create(
        cls,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        input_cost_per_1m: float = 0.075,
        output_cost_per_1m: float = 0.30,
        **kwargs,
    ) -> "CostRecord":
        """
        Factory method that auto-calculates costs.
        """
        input_cost = (input_tokens / 1_000_000) * input_cost_per_1m
        output_cost = (output_tokens / 1_000_000) * output_cost_per_1m

        return cls(
            timestamp=datetime.now().isoformat(),
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=input_cost + output_cost,
            **kwargs,
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON persistence."""
        result = {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "input_cost": round(self.input_cost, 8),
            "output_cost": round(self.output_cost, 8),
            "total_cost": round(self.total_cost, 8),
        }
        if self.thread_id:
            result["thread_id"] = self.thread_id
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class CostSummary:
    """
    R3: Aggregated cost statistics.
    Created by: CostTracker.get_summary()
    Used by: Main orchestrator (display), Logging
    """

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    session_calls: int = 0  # Calls in current session
    session_cost: float = 0.0  # Cost in current session
    cost_by_operation: dict = field(default_factory=dict)  # {"classify": 0.001, ...}
    avg_cost_per_call: float = 0.0
    avg_tokens_per_call: float = 0.0

    def to_dict(self) -> dict:
        """Serialize for display/logging."""
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": f"${self.total_cost:.6f}",
            "session_calls": self.session_calls,
            "session_cost": f"${self.session_cost:.6f}",
            "cost_by_operation": {
                k: f"${v:.6f}" for k, v in self.cost_by_operation.items()
            },
            "avg_cost_per_call": f"${self.avg_cost_per_call:.6f}",
            "avg_tokens_per_call": round(self.avg_tokens_per_call, 1),
        }

    def display_string(self) -> str:
        """Human-readable cost summary for console output."""
        lines = [
            "╔══════════════════════════════════════╗",
            "║         API COST SUMMARY             ║",
            "╠══════════════════════════════════════╣",
            f"║  Session calls:   {self.session_calls:<18}║",
            f"║  Session cost:    ${self.session_cost:<17.6f}║",
            f"║  Total calls:     {self.total_calls:<18}║",
            f"║  Total cost:      ${self.total_cost:<17.6f}║",
            f"║  Total tokens:    {self.total_tokens:<18}║",
            f"║  Avg $/call:      ${self.avg_cost_per_call:<17.6f}║",
            "╠══════════════════════════════════════╣",
            "║  Cost by Operation:                  ║",
        ]
        for op, cost in self.cost_by_operation.items():
            lines.append(f"║    {op:<16} ${cost:<15.6f}║")
        lines.append("╚══════════════════════════════════════╝")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# RULE MATCHING (unchanged — R6)
# ──────────────────────────────────────────────


@dataclass
class MatchedRule:
    """
    A rule from config that matched a classification.
    Created by: RuleEngine
    Used by: SafetyModule, ActionExecutor
    """

    rule_name: str  # Name of the rule from config
    action: str  # "reply" / "draft_reply" / "archive" / "flag" / "ignore"
    auto_send: bool = False  # Should we send without human review?
    template: Optional[str] = None  # Optional response template name
    conditions_matched: dict = field(
        default_factory=dict
    )  # What conditions triggered this


# ──────────────────────────────────────────────
# SAFETY DECISION (unchanged — R6)
# ──────────────────────────────────────────────


@dataclass
class SafetyDecision:
    """
    Result of safety checks — should we proceed with the action?
    Created by: SafetyModule
    Used by: Main orchestrator, ActionExecutor
    """

    can_execute: bool  # Is it safe to take the action?
    can_auto_send: bool  # Specifically: safe to SEND an email?
    reasons: list = field(
        default_factory=list
    )  # ["confidence_ok", "rate_limit_ok", ...]
    warnings: list = field(default_factory=list)  # Non-blocking concerns


# ──────────────────────────────────────────────
# PROCESSING RESULT (enhanced)
# ──────────────────────────────────────────────


@dataclass
class ProcessingResult:
    """
    Complete record of what happened when we processed one email.
    This is what gets logged to the audit trail.
    Created by: Main orchestrator
    Used by: AuditLogger, Display
    """

    email: EmailData
    classification: Optional[ClassificationResult] = None
    matched_rule: Optional[MatchedRule] = None
    safety_decision: Optional[SafetyDecision] = None
    action_taken: str = "none"  # What actually happened
    reply_generated: Optional[str] = None  # The reply text if one was created
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error_message: Optional[str] = None  # If something went wrong

    # ── R3: Cost tracking ─────────────────────────
    cost_data: Optional[CostRecord] = None  # Cost for this email's processing

    # ── R4: Function call action suggestion ───────
    action_suggestion: Optional[ActionSuggestion] = None  # From function calling

    # ── R2: Thread info ───────────────────────────
    thread_context_used: bool = False
    thread_depth: int = 0

    def to_dict(self) -> dict:
        """Serialize for audit logging."""
        result = {
            "timestamp": self.timestamp,
            "success": self.success,
            "action_taken": self.action_taken,
            "email": {
                "id": self.email.id,
                "from": self.email.from_address,
                "subject": self.email.subject,
                "is_thread": self.email.is_part_of_thread,
                "thread_depth": self.email.thread_depth,
            },
        }

        if self.classification:
            result["classification"] = self.classification.to_dict()

        if self.matched_rule:
            result["matched_rule"] = {
                "name": self.matched_rule.rule_name,
                "action": self.matched_rule.action,
            }

        if self.safety_decision:
            result["safety"] = {
                "can_execute": self.safety_decision.can_execute,
                "can_auto_send": self.safety_decision.can_auto_send,
                "reasons": self.safety_decision.reasons,
                "warnings": self.safety_decision.warnings,
            }

        if self.cost_data:
            result["cost"] = self.cost_data.to_dict()

        if self.action_suggestion:
            result["action_suggestion"] = self.action_suggestion.to_dict()

        if self.reply_generated:
            result["reply_length"] = len(self.reply_generated)

        if self.error_message:
            result["error"] = self.error_message

        return result


# ──────────────────────────────────────────────
# R7: FEATURE FLAGS
# ──────────────────────────────────────────────


@dataclass
class FeatureFlags:
    """
    R7: Typed configuration for feature toggles.
    Created by: ConfigManager (from config.yaml "features" section)
    Used by: GeminiAgent, Main orchestrator

    All features default to safe values that preserve backward compatibility.
    """

    use_json_mode: bool = True  # R1: Use Gemini JSON mode for classification
    use_function_calling: bool = True  # R4: Use function calling for action suggestions
    enable_cost_tracking: bool = True  # R3: Track API costs
    thread_context_depth: int = 5  # R2: How many previous messages to include (0-10)

    def __post_init__(self):
        """R7: Validate and clamp values."""
        # Clamp thread depth to valid range
        self.thread_context_depth = max(0, min(10, self.thread_context_depth))

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureFlags":
        """
        Create from config dictionary.
        Handles missing keys with defaults.
        """
        return cls(
            use_json_mode=data.get("use_json_mode", True),
            use_function_calling=data.get("use_function_calling", True),
            enable_cost_tracking=data.get("enable_cost_tracking", True),
            thread_context_depth=data.get("thread_context_depth", 5),
        )

    @classmethod
    def all_disabled(cls) -> "FeatureFlags":
        """Create with all enhancements disabled (pure legacy mode)."""
        return cls(
            use_json_mode=False,
            use_function_calling=False,
            enable_cost_tracking=False,
            thread_context_depth=0,
        )

    def to_dict(self) -> dict:
        """Serialize for logging/display."""
        return {
            "use_json_mode": self.use_json_mode,
            "use_function_calling": self.use_function_calling,
            "enable_cost_tracking": self.enable_cost_tracking,
            "thread_context_depth": self.thread_context_depth,
        }

    def display_string(self) -> str:
        """Human-readable feature status."""

        def status(flag: bool) -> str:
            return "✅ ON" if flag else "❌ OFF"

        return (
            f"  JSON Mode:        {status(self.use_json_mode)}\n"
            f"  Function Calling: {status(self.use_function_calling)}\n"
            f"  Cost Tracking:    {status(self.enable_cost_tracking)}\n"
            f"  Thread Depth:     {self.thread_context_depth} messages"
        )
