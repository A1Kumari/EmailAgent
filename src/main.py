import sys
import os
import argparse
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force UTF-8 encoding for Windows consoles to support emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.config_manager import ConfigManager
from src.gmail_client import GmailClient
from src.gemini_agent import GeminiAgent
from src.rule_engine import RuleEngine
from src.safety import SafetyModule
from src.audit_logger import AuditLogger
from src.models import ProcessingResult
import src.display as display


class EmailAgent:
    """
    Main email automation agent.
    Coordinates all modules to process emails autonomously.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize the agent with all its modules."""

        # ── Step 1: Load Configuration ──
        self.config = ConfigManager(config_path=config_path).load()

        # ── Step 2: Setup Logging ──
        self._setup_logging()

        # ── Step 3: Initialize Modules ──
        self.gmail = GmailClient(self.config.gmail)
        self.gemini = GeminiAgent(self.config.gemini)
        self.rules = RuleEngine(self.config.rules)
        self.safety = SafetyModule(self.config.safety)
        self.audit = AuditLogger(self.config.logging)

        self.logger = logging.getLogger(__name__)

    def _setup_logging(self):
        """Configure console logging with UTF-8 support."""
        import sys

        log_level = getattr(
            logging,
            self.config.logging.console_level.upper(),
            logging.INFO,
        )

        # Force UTF-8 encoding for console handler (fixes Windows issue)
        console_handler = logging.StreamHandler(
            stream=open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
        )
        console_handler.setLevel(log_level)
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-5s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )

        logging.basicConfig(
            level=log_level,
            handlers=[console_handler],
        )

    # ──────────────────────────────────────────────
    # MAIN RUN METHOD
    # ──────────────────────────────────────────────

    def run(self):
        """
        Main execution method.
        Fetches emails, processes each one, and displays results.
        """

        # ── Show Startup Banner ──
        display.show_startup_banner(self.config)
        display.show_rules_summary(self.config.rules)

        # ── Test Connections ──
        self.logger.info("Testing connections...")
        gmail_status = self.gmail.test_connection()
        gmail_ok = gmail_status["imap"] and gmail_status["smtp"]
        gemini_ok = self.gemini.test_connection()
        display.show_connection_status(gmail_ok, gemini_ok)

        if not gmail_ok:
            self.logger.error("Gmail connection failed. Cannot proceed.")
            print("\n❌ Gmail connection failed. Check your credentials in .env")
            return

        if not gemini_ok:
            self.logger.error("Gemini connection failed. Cannot proceed.")
            print("\n❌ Gemini API connection failed. Check your API key in .env")
            return

        # ── Fetch Emails ──
        self.logger.info("Fetching unread emails...")
        emails = self.gmail.fetch_unread_emails(
            mailbox=self.config.processing.mailbox,
            max_count=self.config.processing.max_emails_per_run,
        )
        display.show_email_count(len(emails))

        if not emails:
            return

        # ── Process Each Email ──
        results = []
        for i, email_data in enumerate(emails, 1):
            result = self._process_single_email(email_data, i, len(emails))
            results.append(result)

            # Log to audit trail
            self.audit.log_result(result)

        # ── Show Summary ──
        display.show_run_summary(results, self.config.safety.dry_run)
        self.audit.log_summary(results, self.config.safety.dry_run)

    # ──────────────────────────────────────────────
    # PROCESS SINGLE EMAIL
    # ──────────────────────────────────────────────

    def _process_single_email(
        self,
        email_data,
        index: int,
        total: int,
    ) -> ProcessingResult:
        """Process a single email through the full pipeline."""

        display.show_email_divider(index, total)
        display.show_incoming_email(email_data)

        # Fetch thread context if this is a reply
        if email_data.in_reply_to:
            self.logger.info("Fetching thread context...")
            email_data.thread_messages = self.gmail.fetch_thread_context(
                email_data.in_reply_to
            )
            if email_data.thread_messages:
                self.logger.info(
                    f"Found {len(email_data.thread_messages)} previous message(s) in thread"
                )

        try:
            # Step 1: CLASSIFY
            self.logger.info(f"Classifying email from {email_data.from_address}...")
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
            action_taken, reply_text = self._execute_action(
                email_data, classification, matched_rule, safety_decision
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
            self.logger.error(f"Error processing email: {e}")
            display.show_processing_error(email_data, str(e))
            return ProcessingResult(
                email=email_data,
                action_taken="error",
                success=False,
                error_message=str(e),
            )

    def _execute_action(
        self,
        email_data,
        classification,
        matched_rule,
        safety_decision,
    ) -> tuple:
        """Execute the appropriate action."""

        action = matched_rule.action
        reply_text = None
        dry_run = self.config.safety.dry_run

        # ── IGNORE ──
        if action == "ignore":
            display.show_action_result("ignored", dry_run)
            return "ignored", None

        # ── FLAG ONLY ──
        if action == "flag":
            if safety_decision.can_execute:
                display.show_action_result("flagged", dry_run)
                return "flagged", None
            else:
                display.show_action_result("skipped", dry_run)
                return "skipped", None

        # ── ARCHIVE ──
        if action == "archive":
            if safety_decision.can_execute and not dry_run:
                success = self.gmail.archive_email(email_data.id)
                action_taken = "archived" if success else "error"
            elif safety_decision.can_execute:
                action_taken = "archived"
            else:
                action_taken = "skipped"
            display.show_action_result(action_taken, dry_run)
            return action_taken, None

        # ── REPLY / DRAFT_REPLY / FLAG_AND_DRAFT ──
        if action in ("reply", "draft_reply", "flag_and_draft"):
            # Generate the reply
            self.logger.info("Generating reply...")

            # When generating reply, check for template
            template_name = matched_rule.template
            template_text = None
            if template_name and template_name in self.config.templates:
                template_text = self.config.templates[template_name]

            reply_text = self.gemini.generate_reply(
                email_data, classification, template=template_text
            )

            if not reply_text:
                self.logger.warning("Failed to generate reply")
                display.show_action_result("error", dry_run)
                return "error", None

            # Determine if we should send
            should_send = safety_decision.can_auto_send and not dry_run
            is_just_draft = (
                action in ("draft_reply", "flag_and_draft")
                and not matched_rule.auto_send
            )

            # Show the reply
            display.show_reply_being_sent(
                original_email=email_data,
                reply_text=reply_text,
                is_sending=should_send and not is_just_draft,
                dry_run=dry_run,
            )

            # Actually send if allowed
            if should_send and not is_just_draft:
                to_address = GmailClient.extract_email_address(email_data.from_address)
                reply_subject = GmailClient.make_reply_subject(email_data.subject)

                success = self.gmail.send_reply(
                    to_address=to_address,
                    subject=reply_subject,
                    body=reply_text,
                    in_reply_to=email_data.message_id,
                    references=email_data.references,
                )

                if success:
                    self.safety.record_send()
                    display.show_send_result(True, to_address)
                    action_taken = "reply_sent"
                else:
                    display.show_send_result(False, to_address)
                    action_taken = "error"

            elif action == "flag_and_draft":
                display.show_action_result("flagged_and_drafted", dry_run)
                action_taken = "flagged_and_drafted"
            else:
                display.show_action_result("draft_saved", dry_run)
                action_taken = "draft_saved"

            return action_taken, reply_text

        # ── UNKNOWN ──
        self.logger.warning(f"Unknown action: {action}")
        display.show_action_result("skipped", dry_run)
        return "skipped", reply_text


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────


def main():
    """Entry point for the application."""
    parser = argparse.ArgumentParser(description="Email Automation Agent")
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file (default: config/config.yaml)",
    )
    args = parser.parse_args()

    try:
        agent = EmailAgent(config_path=args.config)
        agent.run()

    except FileNotFoundError as e:
        print(f"\n❌ Configuration error: {e}")
        sys.exit(1)

    except ValueError as e:
        print(f"\n❌ Configuration validation error:\n{e}")
        sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n\n👋 Agent stopped by user.")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        logging.getLogger(__name__).exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
