# src/models.py

"""
Data models used across all modules.
These define the SHAPE of data flowing through the system.
No business logic here — just data structures.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class EmailData:
    """
    Represents a single email fetched from Gmail.
    Created by: GmailClient
    Used by: GeminiAgent, Main orchestrator
    """
    id: str                                    # IMAP message ID
    from_address: str                          # "John Doe <john@company.com>"
    to_address: str                            # "agent@gmail.com"
    subject: str                               # Email subject line
    body: str                                  # Plain text body content
    date: str                                  # When email was received
    message_id: Optional[str] = None           # Unique email ID (for threading)
    in_reply_to: Optional[str] = None          # Message-ID this replies to
    references: Optional[str] = None           # Full thread reference chain
    thread_messages: list = field(default_factory=list)  # Previous messages in thread


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
    intent: str                                # Category of the email
    priority: str                              # "high" / "medium" / "low"
    confidence: float                          # 0.0 to 1.0 — how sure the AI is
    entities: dict = field(default_factory=lambda: {
        "dates": [],
        "names": [],
        "action_items": []
    })
    suggested_action: str = "none"             # What AI recommends doing
    reasoning: str = ""                        # Why AI classified this way


@dataclass
class MatchedRule:
    """
    A rule from config that matched a classification.
    Created by: RuleEngine
    Used by: SafetyModule, ActionExecutor
    """
    rule_name: str                             # Name of the rule from config
    action: str                                # "reply" / "draft_reply" / "archive" / "flag" / "ignore"
    auto_send: bool = False                    # Should we send without human review?
    template: Optional[str] = None             # Optional response template name
    conditions_matched: dict = field(default_factory=dict)  # What conditions triggered this


@dataclass
class SafetyDecision:
    """
    Result of safety checks — should we proceed with the action?
    Created by: SafetyModule
    Used by: Main orchestrator, ActionExecutor
    """
    can_execute: bool                          # Is it safe to take the action?
    can_auto_send: bool                        # Specifically: safe to SEND an email?
    reasons: list = field(default_factory=list) # ["confidence_ok", "rate_limit_ok", ...]
    warnings: list = field(default_factory=list) # Non-blocking concerns


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
    action_taken: str = "none"                 # What actually happened
    reply_generated: Optional[str] = None      # The reply text if one was created
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error_message: Optional[str] = None        # If something went wrong