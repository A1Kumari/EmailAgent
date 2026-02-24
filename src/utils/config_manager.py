# src/utils/config_manager.py

"""
Configuration Manager (Enhanced)

Loads settings from .env (secrets) and config.yaml (behavior).
Validates that all required settings are present.
Provides a single config object for all modules.

Enhanced with:
  - R3: Cost tracking configuration
  - R5: Docker environment variable validation
  - R7: Feature flags for toggling enhancements
  - R8: Graceful defaults for all new settings
  - R9: Startup logging of feature status
"""

import os
import logging
import yaml
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Optional

from src.core.models import FeatureFlags

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# CONFIGURATION DATACLASSES
# ──────────────────────────────────────────────


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


# ── R3: NEW ──────────────────────────────────


@dataclass
class CostTrackingConfig:
    """
    R3: Cost tracking settings.
    Controls how API costs are tracked and persisted.
    """

    enabled: bool = True  # Master on/off switch
    log_dir: str = "logs"  # Where to save cost data
    input_cost_per_1m: float = 0.075  # $ per 1M input tokens
    output_cost_per_1m: float = 0.30  # $ per 1M output tokens
    max_records: int = 500  # Max records to keep in file
    display_on_exit: bool = True  # Show cost summary on shutdown


# ── R7: NEW ──────────────────────────────────


@dataclass
class FeaturesConfig:
    """
    R7: Feature flags for toggling enhancements.
    All features default to enabled (True) for new installs.
    Existing users who lack this section get the same defaults.
    """

    use_json_mode: bool = True  # R1: Gemini JSON mode
    use_function_calling: bool = True  # R4: Function calling
    enable_cost_tracking: bool = True  # R3: Cost tracking
    thread_context_depth: int = 5  # R2: Thread messages to include (0-10)

    def __post_init__(self):
        """Validate and clamp values."""
        self.thread_context_depth = max(0, min(10, self.thread_context_depth))

    def to_feature_flags(self) -> FeatureFlags:
        """Convert to FeatureFlags model (used by GeminiAgent)."""
        return FeatureFlags(
            use_json_mode=self.use_json_mode,
            use_function_calling=self.use_function_calling,
            enable_cost_tracking=self.enable_cost_tracking,
            thread_context_depth=self.thread_context_depth,
        )

    def to_dict(self) -> dict:
        """Convert to dict (used by GeminiAgent feature_flags param)."""
        return {
            "use_json_mode": self.use_json_mode,
            "use_function_calling": self.use_function_calling,
            "enable_cost_tracking": self.enable_cost_tracking,
            "thread_context_depth": self.thread_context_depth,
        }


# ──────────────────────────────────────────────
# APP CONFIG (enhanced)
# ──────────────────────────────────────────────


@dataclass
class AppConfig:
    """
    Complete application configuration.

    Enhanced with:
      - features: R7 feature flags
      - cost_tracking: R3 cost tracking settings
    """

    gmail: GmailConfig
    gemini: GeminiConfig
    safety: SafetyConfig
    processing: ProcessingConfig
    logging: LoggingConfig
    rules: list
    templates: dict = field(default_factory=dict)

    # ── R7: Feature flags (new, optional) ─────────
    features: FeaturesConfig = field(default_factory=FeaturesConfig)

    # ── R3: Cost tracking config (new, optional) ──
    cost_tracking: CostTrackingConfig = field(default_factory=CostTrackingConfig)


# ──────────────────────────────────────────────
# CONFIG MANAGER
# ──────────────────────────────────────────────


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
      - R7: Feature flags (new, optional section)
      - R3: Cost tracking settings (new, optional section)
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

        # R9: Log feature status at startup
        self._log_startup_status(config)

        return config

    def _load_env(self):
        """Load environment variables from .env file."""
        if os.path.exists(self.env_path):
            load_dotenv(self.env_path)
        else:
            # .env might not exist if using system env vars (e.g., Docker)
            print(
                f"⚠️  No .env file found at {self.env_path}, "
                f"using system environment variables"
            )

    def _load_yaml(self) -> dict:
        """Load and parse config.yaml file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Copy config/config.example.yaml to config/config.yaml "
                f"and fill in your settings."
            )

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        if config is None:
            raise ValueError(f"Configuration file is empty: {self.config_path}")

        return config

    def _build_config(self, yaml_config: dict) -> AppConfig:
        """Combine .env secrets and yaml settings into AppConfig."""

        # ── Gmail config ──────────────────────────
        gmail = GmailConfig(
            email=os.getenv("GMAIL_EMAIL", ""),
            app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
        )

        # ── Gemini config ─────────────────────────
        gemini_yaml = yaml_config.get("gemini", {})
        gemini = GeminiConfig(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model=gemini_yaml.get("model", "gemini-2.5-flash"),
            temperature=gemini_yaml.get("temperature", 0.3),
            max_tokens=gemini_yaml.get("max_tokens", 1024),
        )

        # ── Safety config ─────────────────────────
        # DRY_RUN can be overridden from .env
        safety_yaml = yaml_config.get("safety", {})
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

        # ── Processing config ─────────────────────
        processing_yaml = yaml_config.get("processing", {})
        processing = ProcessingConfig(
            mode=processing_yaml.get("mode", "unread"),
            max_emails_per_run=processing_yaml.get("max_emails_per_run", 10),
            mailbox=processing_yaml.get("mailbox", "INBOX"),
        )

        # ── Logging config ────────────────────────
        logging_yaml = yaml_config.get("logging", {})
        logging_config = LoggingConfig(
            console_level=logging_yaml.get("console_level", "INFO"),
            file_level=logging_yaml.get("file_level", "DEBUG"),
            log_dir=logging_yaml.get("log_dir", "logs"),
        )

        # ── Rules ─────────────────────────────────
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

        # ── Templates ─────────────────────────────
        templates = yaml_config.get("templates", {})

        # ── R7: Feature flags (NEW) ───────────────
        features = self._build_features_config(yaml_config)

        # ── R3: Cost tracking (NEW) ───────────────
        cost_tracking = self._build_cost_config(yaml_config, logging_config)

        # Sync: if cost tracking is disabled in features, disable in cost config too
        if not features.enable_cost_tracking:
            cost_tracking.enabled = False

        return AppConfig(
            gmail=gmail,
            gemini=gemini,
            safety=safety,
            processing=processing,
            logging=logging_config,
            rules=rules,
            templates=templates,
            features=features,
            cost_tracking=cost_tracking,
        )

    # ── R7: Feature flags parsing ─────────────────

    def _build_features_config(self, yaml_config: dict) -> FeaturesConfig:
        """
        R7: Parse the 'features' section from config.yaml.
        If the section is missing, return safe defaults (all enabled).
        This ensures backward compatibility with existing config files.

        Expected config.yaml format:
            features:
              use_json_mode: true
              use_function_calling: true
              enable_cost_tracking: true
              thread_context_depth: 5
        """
        features_yaml = yaml_config.get("features", {})

        if not features_yaml:
            logger.debug(
                "[R7] No 'features' section in config.yaml — "
                "using defaults (all features enabled)"
            )
            return FeaturesConfig()

        # Also check for env var overrides (useful for Docker)
        json_mode_env = os.getenv("FEATURE_JSON_MODE", None)
        func_calling_env = os.getenv("FEATURE_FUNCTION_CALLING", None)
        cost_tracking_env = os.getenv("FEATURE_COST_TRACKING", None)
        thread_depth_env = os.getenv("FEATURE_THREAD_DEPTH", None)

        def _parse_bool(env_val: Optional[str], yaml_val, default: bool) -> bool:
            """Environment variable overrides yaml, which overrides default."""
            if env_val is not None:
                return env_val.lower() not in ("false", "0", "no", "off")
            if yaml_val is not None:
                return bool(yaml_val)
            return default

        def _parse_int(env_val: Optional[str], yaml_val, default: int) -> int:
            """Environment variable overrides yaml, which overrides default."""
            if env_val is not None:
                try:
                    return int(env_val)
                except ValueError:
                    return default
            if yaml_val is not None:
                try:
                    return int(yaml_val)
                except (ValueError, TypeError):
                    return default
            return default

        return FeaturesConfig(
            use_json_mode=_parse_bool(
                json_mode_env,
                features_yaml.get("use_json_mode"),
                True,
            ),
            use_function_calling=_parse_bool(
                func_calling_env,
                features_yaml.get("use_function_calling"),
                True,
            ),
            enable_cost_tracking=_parse_bool(
                cost_tracking_env,
                features_yaml.get("enable_cost_tracking"),
                True,
            ),
            thread_context_depth=_parse_int(
                thread_depth_env,
                features_yaml.get("thread_context_depth"),
                5,
            ),
        )

    # ── R3: Cost tracking config parsing ──────────

    def _build_cost_config(
        self, yaml_config: dict, logging_config: LoggingConfig
    ) -> CostTrackingConfig:
        """
        R3: Parse the 'cost_tracking' section from config.yaml.
        If missing, returns defaults (enabled, using logs directory).

        Expected config.yaml format:
            cost_tracking:
              enabled: true
              log_dir: "logs"
              input_cost_per_1m: 0.075
              output_cost_per_1m: 0.30
              max_records: 500
              display_on_exit: true
        """
        cost_yaml = yaml_config.get("cost_tracking", {})

        if not cost_yaml:
            logger.debug(
                "[R3] No 'cost_tracking' section in config.yaml — using defaults"
            )
            return CostTrackingConfig(
                log_dir=logging_config.log_dir,
            )

        return CostTrackingConfig(
            enabled=cost_yaml.get("enabled", True),
            log_dir=cost_yaml.get("log_dir", logging_config.log_dir),
            input_cost_per_1m=float(cost_yaml.get("input_cost_per_1m", 0.075)),
            output_cost_per_1m=float(cost_yaml.get("output_cost_per_1m", 0.30)),
            max_records=int(cost_yaml.get("max_records", 500)),
            display_on_exit=cost_yaml.get("display_on_exit", True),
        )

    # ──────────────────────────────────────────────
    # VALIDATION
    # ──────────────────────────────────────────────

    def _validate(self, config: AppConfig):
        """Validate that all required configuration is present."""
        errors = []

        # ── Check Gmail credentials ───────────────
        if not config.gmail.email:
            errors.append("GMAIL_EMAIL is missing in .env")
        if not config.gmail.app_password:
            errors.append("GMAIL_APP_PASSWORD is missing in .env")

        # ── Check Gemini credentials ──────────────
        if not config.gemini.api_key:
            errors.append("GEMINI_API_KEY is missing in .env")

        # ── Check safety settings ─────────────────
        if not 0.0 <= config.safety.confidence_threshold <= 1.0:
            errors.append("confidence_threshold must be between 0.0 and 1.0")
        if config.safety.max_sends_per_hour < 1:
            errors.append("max_sends_per_hour must be at least 1")

        # ── Check rules exist ─────────────────────
        if not config.rules:
            errors.append("No rules defined in config.yaml")

        # ── Check each rule ───────────────────────
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
                    f"Rule '{rule.name}' has invalid action: '{rule.action}'. "
                    f"Must be one of {valid_actions}"
                )

        # ── R7: Validate feature flags ────────────
        self._validate_features(config.features, errors)

        # ── R3: Validate cost tracking config ─────
        self._validate_cost_config(config.cost_tracking, errors)

        # ── If any errors, fail fast ──────────────
        if errors:
            error_msg = "Configuration errors found:\n"
            for error in errors:
                error_msg += f"  ❌ {error}\n"
            raise ValueError(error_msg)

    def _validate_features(self, features: FeaturesConfig, errors: list):
        """
        R7: Validate feature flag values.
        Provides sensible defaults rather than failing for most issues.
        """
        # Thread depth must be in valid range (already clamped in __post_init__,
        # but warn if the original value was out of range)
        if not isinstance(features.thread_context_depth, int):
            errors.append(
                f"thread_context_depth must be an integer, "
                f"got: {type(features.thread_context_depth).__name__}"
            )

        # Boolean checks (defensive — shouldn't happen with proper parsing)
        for flag_name in [
            "use_json_mode",
            "use_function_calling",
            "enable_cost_tracking",
        ]:
            val = getattr(features, flag_name, None)
            if not isinstance(val, bool):
                errors.append(
                    f"Feature flag '{flag_name}' must be boolean, "
                    f"got: {type(val).__name__}"
                )

    def _validate_cost_config(self, cost_config: CostTrackingConfig, errors: list):
        """R3: Validate cost tracking configuration."""
        if cost_config.input_cost_per_1m < 0:
            errors.append("cost_tracking.input_cost_per_1m cannot be negative")
        if cost_config.output_cost_per_1m < 0:
            errors.append("cost_tracking.output_cost_per_1m cannot be negative")
        if cost_config.max_records < 1:
            errors.append("cost_tracking.max_records must be at least 1")

    # ──────────────────────────────────────────────
    # R5: DOCKER ENVIRONMENT VALIDATION
    # ──────────────────────────────────────────────

    @staticmethod
    def validate_docker_env() -> tuple[bool, list[str]]:
        """
        R5 (AC6): Validate that required environment variables are present.
        Used by Docker entrypoint to fail fast with a clear error message.

        Returns:
            Tuple of (is_valid, list_of_missing_vars)

        Usage in Docker entrypoint or main.py:
            is_valid, missing = ConfigManager.validate_docker_env()
            if not is_valid:
                print(f"Missing env vars: {missing}")
                sys.exit(1)
        """
        required_vars = [
            "GMAIL_EMAIL",
            "GMAIL_APP_PASSWORD",
            "GEMINI_API_KEY",
        ]

        missing = [var for var in required_vars if not os.getenv(var)]

        if missing:
            return False, missing
        return True, []

    # ──────────────────────────────────────────────
    # R9: STARTUP LOGGING
    # ──────────────────────────────────────────────

    def _log_startup_status(self, config: AppConfig):
        """
        R9: Log configuration status at startup.
        Shows which features are enabled and key settings.
        """
        logger.info("=" * 50)
        logger.info("CONFIGURATION LOADED")
        logger.info("=" * 50)

        # Core settings
        logger.info(f"  Gmail:      {config.gmail.email}")
        logger.info(f"  Model:      {config.gemini.model}")
        logger.info(f"  Dry run:    {config.safety.dry_run}")
        logger.info(f"  Confidence: {config.safety.confidence_threshold}")
        logger.info(f"  Rules:      {len(config.rules)} rules loaded")

        # R7: Feature flags status
        logger.info("-" * 50)
        logger.info("FEATURE FLAGS:")
        logger.info(
            f"  JSON Mode:        "
            f"{'✅ ON' if config.features.use_json_mode else '❌ OFF'}"
        )
        logger.info(
            f"  Function Calling: "
            f"{'✅ ON' if config.features.use_function_calling else '❌ OFF'}"
        )
        logger.info(
            f"  Cost Tracking:    "
            f"{'✅ ON' if config.features.enable_cost_tracking else '❌ OFF'}"
        )
        logger.info(
            f"  Thread Depth:     {config.features.thread_context_depth} messages"
        )

        # R3: Cost tracking status
        if config.features.enable_cost_tracking:
            logger.info("-" * 50)
            logger.info("COST TRACKING:")
            logger.info(f"  Log dir:      {config.cost_tracking.log_dir}")
            logger.info(
                f"  Input price:  ${config.cost_tracking.input_cost_per_1m}/1M tokens"
            )
            logger.info(
                f"  Output price: ${config.cost_tracking.output_cost_per_1m}/1M tokens"
            )

        logger.info("=" * 50)
