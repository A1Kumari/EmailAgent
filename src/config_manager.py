# src/config_manager.py

"""
Configuration Manager
Loads settings from .env (secrets) and config.yaml (behavior).
Validates that all required settings are present.
Provides a single config object for all modules.
"""

import os
import yaml
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GmailConfig:
    """Gmail connection settings."""

    email: str
    app_password: str
    imap_server: str = "imap.gmail.com"
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 465


@dataclass
class GeminiConfig:
    """Gemini AI settings."""

    api_key: str
    model: str = "gemini-2.5-flash"
    temperature: float = 0.3
    max_tokens: int = 1024


@dataclass
class SafetyConfig:
    """Safety and control settings."""

    dry_run: bool = True
    confidence_threshold: float = 0.85
    max_sends_per_hour: int = 20


@dataclass
class ProcessingConfig:
    """Email processing settings."""

    mode: str = "unread"
    max_emails_per_run: int = 10
    mailbox: str = "INBOX"


@dataclass
class LoggingConfig:
    """Logging settings."""

    console_level: str = "INFO"
    file_level: str = "DEBUG"
    log_dir: str = "logs"


@dataclass
class RuleConfig:
    """Single automation rule."""

    name: str
    conditions: dict
    action: str
    auto_send: bool = False
    template: Optional[str] = None


@dataclass
class AppConfig:
    """Complete application configuration."""

    gmail: GmailConfig
    gemini: GeminiConfig
    safety: SafetyConfig
    processing: ProcessingConfig
    logging: LoggingConfig
    rules: list
    templates: dict = field(default_factory=dict)


class ConfigManager:
    """
    Loads and validates all configuration.

    Secrets come from .env file:
      - GMAIL_EMAIL
      - GMAIL_APP_PASSWORD
      - GEMINI_API_KEY

    Behavior comes from config.yaml:
      - Processing settings
      - Safety settings
      - Rules
      - Logging settings
    """

    def __init__(self, config_path: str = "config/config.yaml", env_path: str = ".env"):
        self.config_path = config_path
        self.env_path = env_path

    def load(self) -> AppConfig:
        """Load and validate all configuration. Returns AppConfig object."""

        # Step 1: Load secrets from .env
        self._load_env()

        # Step 2: Load behavior from config.yaml
        yaml_config = self._load_yaml()

        # Step 3: Build typed config objects
        config = self._build_config(yaml_config)

        # Step 4: Validate everything is present
        self._validate(config)

        return config

    def _load_env(self):
        """Load environment variables from .env file."""
        if os.path.exists(self.env_path):
            load_dotenv(self.env_path)
        else:
            # .env might not exist if using system env vars
            print(
                f"⚠️  No .env file found at {self.env_path}, using system environment variables"
            )

    def _load_yaml(self) -> dict:
        """Load and parse config.yaml file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Copy config/config.example.yaml to config/config.yaml and fill in your settings."
            )

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        if config is None:
            raise ValueError(f"Configuration file is empty: {self.config_path}")

        return config

    def _build_config(self, yaml_config: dict) -> AppConfig:
        """Combine .env secrets and yaml settings into AppConfig."""

        # Gmail config
        gmail = GmailConfig(
            email=os.getenv("GMAIL_EMAIL", ""),
            app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
        )

        # Gemini config
        gemini_yaml = yaml_config.get("gemini", {})
        gemini = GeminiConfig(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model=gemini_yaml.get("model", "gemini-2.5-flash"),
            temperature=gemini_yaml.get("temperature", 0.3),
            max_tokens=gemini_yaml.get("max_tokens", 1024),
        )

        # Safety config — DRY_RUN can be overridden from .env
        safety_yaml = yaml_config.get("safety", {})

        # Check .env first, then fall back to config.yaml
        dry_run_env = os.getenv("DRY_RUN", None)
        if dry_run_env is not None:
            dry_run = dry_run_env.lower() not in ("false", "0", "no")
        else:
            dry_run = safety_yaml.get("dry_run", True)

        safety = SafetyConfig(
            dry_run=dry_run,
            confidence_threshold=safety_yaml.get("confidence_threshold", 0.85),
            max_sends_per_hour=safety_yaml.get("max_sends_per_hour", 20),
        )

        # Processing config
        processing_yaml = yaml_config.get("processing", {})
        processing = ProcessingConfig(
            mode=processing_yaml.get("mode", "unread"),
            max_emails_per_run=processing_yaml.get("max_emails_per_run", 10),
            mailbox=processing_yaml.get("mailbox", "INBOX"),
        )

        # Logging config
        logging_yaml = yaml_config.get("logging", {})
        logging_config = LoggingConfig(
            console_level=logging_yaml.get("console_level", "INFO"),
            file_level=logging_yaml.get("file_level", "DEBUG"),
            log_dir=logging_yaml.get("log_dir", "logs"),
        )

        # Rules
        rules = []
        for rule_data in yaml_config.get("rules", []):
            rules.append(
                RuleConfig(
                    name=rule_data.get("name", "Unnamed Rule"),
                    conditions=rule_data.get("conditions", {}),
                    action=rule_data.get("action", "ignore"),
                    auto_send=rule_data.get("auto_send", False),
                    template=rule_data.get("template", None),
                )
            )

        # Templates
        templates = yaml_config.get("templates", {})
        return AppConfig(
            gmail=gmail,
            gemini=gemini,
            safety=safety,
            processing=processing,
            logging=logging_config,
            rules=rules,
            templates=templates,
        )

    def _validate(self, config: AppConfig):
        """Validate that all required configuration is present."""
        errors = []

        # Check Gmail credentials
        if not config.gmail.email:
            errors.append("GMAIL_EMAIL is missing in .env")
        if not config.gmail.app_password:
            errors.append("GMAIL_APP_PASSWORD is missing in .env")

        # Check Gemini credentials
        if not config.gemini.api_key:
            errors.append("GEMINI_API_KEY is missing in .env")

        # Check safety settings are reasonable
        if not 0.0 <= config.safety.confidence_threshold <= 1.0:
            errors.append("confidence_threshold must be between 0.0 and 1.0")
        if config.safety.max_sends_per_hour < 1:
            errors.append("max_sends_per_hour must be at least 1")

        # Check rules exist
        if not config.rules:
            errors.append("No rules defined in config.yaml")

        # Check each rule has required fields
        valid_actions = [
            "reply",
            "draft_reply",
            "archive",
            "flag",
            "flag_and_draft",
            "ignore",
        ]
        for i, rule in enumerate(config.rules):
            if not rule.name:
                errors.append(f"Rule {i + 1} is missing a name")
            if not rule.conditions:
                errors.append(f"Rule '{rule.name}' has no conditions")
            if rule.action not in valid_actions:
                errors.append(
                    f"Rule '{rule.name}' has invalid action: '{rule.action}'. Must be one of {valid_actions}"
                )

        # If any errors, fail fast with clear message
        if errors:
            error_msg = "Configuration errors found:\n"
            for error in errors:
                error_msg += f"  ❌ {error}\n"
            raise ValueError(error_msg)
