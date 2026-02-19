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
from src.email_processor import EmailProcessor
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

        # ── Step 4: Initialize Service Layer ──
        self.processor = EmailProcessor(
            self.config, self.gmail, self.gemini, self.rules, self.safety
        )

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
            # Delegate to the Service Layer
            result = self.processor.process_single_email(email_data, i, len(emails))
            results.append(result)

            # Log to audit trail
            self.audit.log_result(result)

        # ── Show Summary ──
        display.show_run_summary(results, self.config.safety.dry_run)
        self.audit.log_summary(results, self.config.safety.dry_run)


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
