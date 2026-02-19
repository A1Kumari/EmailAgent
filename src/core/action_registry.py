from abc import ABC, abstractmethod
import logging
from typing import Optional, Tuple

from src.clients.gmail_client import GmailClient
from src.clients.gemini_agent import GeminiAgent
from src.core.models import (
    EmailData,
    ClassificationResult,
    MatchedRule,
    SafetyDecision,
    ProcessingResult,
)
import src.utils.display as display

logger = logging.getLogger(__name__)


class ActionExecutor(ABC):
    """Abstract base class for all email actions."""

    @abstractmethod
    def execute(
        self,
        email_data: EmailData,
        classification: ClassificationResult,
        matched_rule: MatchedRule,
        safety_decision: SafetyDecision,
        config,
        clients: dict,
    ) -> Tuple[str, Optional[str]]:
        """
        Execute the action.

        Args:
            email_data: The email being processed
            classification: AI classification result
            matched_rule: The rule that triggered this action
            safety_decision: Safety check result
            config: Full configuration object
            clients: Dict containing initialized clients {'gmail': GmailClient, 'gemini': GeminiAgent, 'safety': SafetyModule}

        Returns:
            Tuple of (action_taken_string, reply_text_if_any)
        """
        pass


class BaseReplyAction(ActionExecutor):
    """Shared logic for reply-based actions."""

    def _generate_reply(
        self,
        email_data: EmailData,
        classification: ClassificationResult,
        matched_rule: MatchedRule,
        config,
        gemini: GeminiAgent,
    ) -> Optional[str]:

        logger.info("Generating reply...")

        # Check for template
        template_name = matched_rule.template
        template_text = None
        if template_name and template_name in config.templates:
            template_text = config.templates[template_name]

        return gemini.generate_reply(email_data, classification, template=template_text)


class ReplyAction(BaseReplyAction):
    """Handles 'reply', 'draft_reply', and 'flag_and_draft' actions."""

    def execute(
        self, email_data, classification, matched_rule, safety_decision, config, clients
    ):
        gmail = clients["gmail"]
        gemini = clients["gemini"]
        safety = clients["safety"]
        dry_run = config.safety.dry_run

        reply_text = self._generate_reply(
            email_data, classification, matched_rule, config, gemini
        )

        if not reply_text:
            logger.warning("Failed to generate reply")
            display.show_action_result("error", dry_run)
            return "error", None

        # Prepare reply details
        to_address = GmailClient.extract_email_address(email_data.from_address)
        reply_subject = GmailClient.make_reply_subject(email_data.subject)

        # Decide: auto-send or save as draft
        should_send = safety_decision.can_auto_send and not dry_run

        # Specific check for actions that are explicitly just drafts/flags
        action_type = matched_rule.action
        is_just_draft = (
            action_type in ("draft_reply", "flag_and_draft")
            and not matched_rule.auto_send
        )

        display.show_reply_being_sent(
            original_email=email_data,
            reply_text=reply_text,
            is_sending=should_send,
            dry_run=dry_run,
        )

        action_taken = "error"

        if should_send:
            # AUTO-SEND
            success = gmail.send_reply(
                to_address=to_address,
                subject=reply_subject,
                body=reply_text,
                in_reply_to=email_data.message_id,
                references=email_data.references,
            )

            if success:
                safety.record_send()
                display.show_send_result(True, to_address)
                action_taken = "reply_sent"
            else:
                display.show_send_result(False, to_address)
                action_taken = "error"

        else:
            # SAVE DRAFT
            if not dry_run:
                draft_saved = gmail.save_draft(
                    to_address=to_address,
                    subject=reply_subject,
                    body=reply_text,
                    in_reply_to=email_data.message_id,
                    references=email_data.references,
                )
                if draft_saved:
                    logger.info("Draft saved to Gmail Drafts folder")
                else:
                    logger.warning("Could not save draft to Gmail")

            if action_type == "flag_and_draft":
                display.show_action_result("flagged_and_drafted", dry_run)
                action_taken = "flagged_and_drafted"
            else:
                display.show_action_result("draft_saved", dry_run)
                action_taken = "draft_saved"

        return action_taken, reply_text


class ArchiveAction(ActionExecutor):
    """Handles 'archive' action."""

    def execute(
        self, email_data, classification, matched_rule, safety_decision, config, clients
    ):
        gmail = clients["gmail"]
        dry_run = config.safety.dry_run

        action_taken = "skipped"

        if safety_decision.can_execute and not dry_run:
            success = gmail.archive_email(email_data.id)
            action_taken = "archived" if success else "error"
        elif safety_decision.can_execute:
            action_taken = "archived"  # Simulated for dry run

        display.show_action_result(action_taken, dry_run)
        return action_taken, None


class FlagAction(ActionExecutor):
    """Handles 'flag' action."""

    def execute(
        self, email_data, classification, matched_rule, safety_decision, config, clients
    ):
        dry_run = config.safety.dry_run

        if safety_decision.can_execute:
            display.show_action_result("flagged", dry_run)
            return "flagged", None
        else:
            display.show_action_result("skipped", dry_run)
            return "skipped", None


class IgnoreAction(ActionExecutor):
    """Handles 'ignore' action."""

    def execute(
        self, email_data, classification, matched_rule, safety_decision, config, clients
    ):
        dry_run = config.safety.dry_run
        display.show_action_result("ignored", dry_run)
        return "ignored", None


class ActionFactory:
    """Factory to create the correct ActionExecutor."""

    @staticmethod
    def get_executor(action_name: str) -> ActionExecutor:
        if action_name in ("reply", "draft_reply", "flag_and_draft"):
            return ReplyAction()
        elif action_name == "archive":
            return ArchiveAction()
        elif action_name == "flag":
            return FlagAction()
        elif action_name == "ignore":
            return IgnoreAction()
        else:
            return None
