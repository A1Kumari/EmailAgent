import logging
from typing import Optional

from src.models import EmailData, ProcessingResult, MatchedRule, SafetyDecision
from src.action_registry import ActionFactory
import src.display as display

logger = logging.getLogger(__name__)


class EmailProcessor:
    """
    Service layer for processing individual emails.
    Orchestrates: Classification -> Rule Matching -> Safety Check -> Action Execution.
    """

    def __init__(self, config, gmail_client, gemini_agent, rule_engine, safety_module):
        self.config = config
        self.gmail = gmail_client
        self.gemini = gemini_agent
        self.rules = rule_engine
        self.safety = safety_module

    def process_single_email(
        self,
        email_data: EmailData,
        index: int,
        total: int,
    ) -> ProcessingResult:
        """Process a single email through the full pipeline."""

        display.show_email_divider(index, total)
        display.show_incoming_email(email_data)

        # Fetch thread context if this is a reply
        if email_data.in_reply_to:
            logger.info("Fetching thread context...")
            email_data.thread_messages = self.gmail.fetch_thread_context(
                email_data.in_reply_to
            )
            if email_data.thread_messages:
                logger.info(
                    f"Found {len(email_data.thread_messages)} previous message(s) in thread"
                )

        try:
            # Step 1: CLASSIFY
            logger.info(f"Classifying email from {email_data.from_address}...")
            classification = self.gemini.classify_email(email_data)
            display.show_ai_analysis(classification)

            # Step 2: MATCH RULES
            matched_rule = self.rules.match(email_data, classification)

            # Step 3: SAFETY CHECK
            safety_decision = None
            if matched_rule:
                safety_decision = self.safety.evaluate(classification, matched_rule)

            display.show_decision(
                matched_rule, safety_decision, self.config.safety.dry_run
            )

            if not matched_rule:
                display.show_action_result("skipped", self.config.safety.dry_run)
                return ProcessingResult(
                    email=email_data,
                    classification=classification,
                    action_taken="skipped",
                )

            # Step 4: EXECUTE
            action_executor = ActionFactory.get_executor(matched_rule.action)

            if not action_executor:
                logger.warning(f"Unknown action: {matched_rule.action}")
                display.show_action_result("skipped", self.config.safety.dry_run)
                return ProcessingResult(
                    email=email_data,
                    classification=classification,
                    matched_rule=matched_rule,
                    safety_decision=safety_decision,
                    action_taken="skipped",
                )

            # Prepare client context for the executor
            clients = {
                "gmail": self.gmail,
                "gemini": self.gemini,
                "safety": self.safety,
            }

            action_taken, reply_text = action_executor.execute(
                email_data,
                classification,
                matched_rule,
                safety_decision,
                self.config,
                clients,
            )

            return ProcessingResult(
                email=email_data,
                classification=classification,
                matched_rule=matched_rule,
                safety_decision=safety_decision,
                action_taken=action_taken,
                reply_generated=reply_text,
                success=True,
            )

        except Exception as e:
            logger.error(f"Error processing email: {e}")
            display.show_processing_error(email_data, str(e))
            return ProcessingResult(
                email=email_data,
                action_taken="error",
                success=False,
                error_message=str(e),
            )
