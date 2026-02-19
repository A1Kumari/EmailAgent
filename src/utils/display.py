# src/display.py

"""
Display Module — Clean, readable console output.
Designed to make it immediately obvious:
  - What email was received
  - What the AI understood
  - What action was taken
  - What reply was sent (if any)
"""

from datetime import datetime
from typing import Optional

from src.core.models import (
    EmailData,
    ClassificationResult,
    MatchedRule,
    SafetyDecision,
    ProcessingResult,
)


# ──────────────────────────────────────────────
# COLORS
# ──────────────────────────────────────────────


class C:
    """ANSI color codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


def col(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


# ──────────────────────────────────────────────
# STARTUP
# ──────────────────────────────────────────────


def show_startup_banner(config):
    """Show startup banner with clear mode indication."""
    is_live = not config.safety.dry_run

    print()
    print(col("+" + "=" * 58 + "+", C.CYAN))
    print(
        col("|", C.CYAN)
        + col("         EMAIL AUTOMATION AGENT v1.0                   ", C.BOLD)
        + col("|", C.CYAN)
    )
    print(col("+" + "=" * 58 + "+", C.CYAN))
    print()

    # MODE — make it very obvious
    if is_live:
        print(
            col(
                "  !! WARNING: LIVE MODE — AGENT WILL SEND REAL EMAILS !!",
                C.BG_RED + C.WHITE + C.BOLD,
            )
        )
        print()
    else:
        print(
            col(
                "  [SAFE] DRY RUN MODE — No emails will actually be sent",
                C.BG_BLUE + C.WHITE,
            )
        )
        print()

    print(f"  Account:      {col(config.gmail.email, C.CYAN)}")
    print(f"  AI Model:     {config.gemini.model}")
    print(f"  Confidence:   {config.safety.confidence_threshold} minimum")
    print(f"  Rate Limit:   {config.safety.max_sends_per_hour} sends/hour")
    print(f"  Rules:        {len(config.rules)} loaded")
    print()


def show_rules_summary(rules: list):
    """Show configured rules in a table."""
    print(col("  Rules Configuration:", C.BOLD))
    print(f"  {'#':<4} {'Rule Name':<35} {'Action':<15} {'Auto-Send'}")
    print(f"  {'--':<4} {'---':<35} {'---':<15} {'---'}")

    for i, rule in enumerate(rules, 1):
        auto = col("YES", C.RED + C.BOLD) if rule.auto_send else col("no", C.GREEN)
        print(f"  {i:<4} {rule.name:<35} {rule.action:<15} {auto}")
    print()


def show_connection_status(gmail_ok: bool, gemini_ok: bool):
    """Show connection test results."""
    g1 = col("[OK]", C.GREEN) if gmail_ok else col("[FAIL]", C.RED)
    g2 = col("[OK]", C.GREEN) if gemini_ok else col("[FAIL]", C.RED)
    print(f"  Gmail:  {g1}")
    print(f"  Gemini: {g2}")
    print()


# ──────────────────────────────────────────────
# PROCESSING EACH EMAIL
# ──────────────────────────────────────────────


def show_email_divider(index: int, total: int):
    """Big clear divider between emails."""
    print()
    print(col("=" * 60, C.CYAN))
    print(col(f"  EMAIL {index} of {total}", C.BOLD + C.CYAN))
    print(col("=" * 60, C.CYAN))


def show_incoming_email(email_data: EmailData):
    """Show the received email clearly."""
    print()
    print(col("  RECEIVED EMAIL:", C.BOLD + C.WHITE))
    print(col("  +" + "-" * 56 + "+", C.DIM))
    print(col("  |", C.DIM) + f" From:    {col(email_data.from_address, C.CYAN)}")
    print(col("  |", C.DIM) + f" Subject: {col(email_data.subject, C.WHITE + C.BOLD)}")
    print(col("  |", C.DIM) + f" Date:    {email_data.date}")
    print(col("  |", C.DIM))

    # Show body — first 5 lines or 300 chars
    body_lines = email_data.body.strip().split("\n")
    body_preview = []
    char_count = 0
    for line in body_lines:
        if char_count > 300 or len(body_preview) >= 5:
            body_preview.append("  ...")
            break
        body_preview.append(line.strip())
        char_count += len(line)

    print(col("  |", C.DIM) + col(f" Body:", C.DIM))
    for line in body_preview:
        print(col("  |", C.DIM) + col(f"   {line}", C.DIM))

    print(col("  +" + "-" * 56 + "+", C.DIM))
    print()


def show_ai_analysis(classification: ClassificationResult):
    """Show what the AI understood about the email."""

    # Color code intent
    intent_colors = {
        "meeting_request": C.BLUE,
        "newsletter": C.DIM,
        "urgent_issue": C.RED,
        "spam": C.YELLOW,
        "general_inquiry": C.CYAN,
        "follow_up": C.MAGENTA,
        "complaint": C.RED,
        "action_required": C.YELLOW,
    }
    intent_color = intent_colors.get(classification.intent, C.WHITE)

    # Color code priority
    priority_display = {
        "high": col("HIGH", C.RED + C.BOLD),
        "medium": col("MEDIUM", C.YELLOW),
        "low": col("LOW", C.GREEN),
    }

    # Color code confidence
    conf = classification.confidence
    if conf >= 0.85:
        conf_display = col(f"{conf:.0%}", C.GREEN + C.BOLD)
    elif conf >= 0.60:
        conf_display = col(f"{conf:.0%}", C.YELLOW)
    else:
        conf_display = col(f"{conf:.0%}", C.RED + C.BOLD)

    print(col("  AI ANALYSIS:", C.BOLD + C.WHITE))
    print(
        f"    Intent:     {col(classification.intent.upper().replace('_', ' '), intent_color + C.BOLD)}"
    )
    print(
        f"    Priority:   {priority_display.get(classification.priority, classification.priority)}"
    )
    print(f"    Confidence: {conf_display}")

    # Entities
    entities = classification.entities
    has_entities = any(
        [
            entities.get("dates"),
            entities.get("names"),
            entities.get("action_items"),
        ]
    )
    if has_entities:
        print(f"    Extracted:")
        if entities.get("dates"):
            print(f"      Dates:   {', '.join(str(d) for d in entities['dates'])}")
        if entities.get("names"):
            print(f"      Names:   {', '.join(str(n) for n in entities['names'])}")
        if entities.get("action_items"):
            print(
                f"      Actions: {', '.join(str(a) for a in entities['action_items'])}"
            )

    # Reasoning — compact
    if classification.reasoning:
        reasoning = classification.reasoning[:120]
        if len(classification.reasoning) > 120:
            reasoning += "..."
        print(f"    Why:        {col(reasoning, C.DIM)}")
    print()


def show_decision(
    matched_rule: Optional[MatchedRule], safety: Optional[SafetyDecision], dry_run: bool
):
    """Show what decision was made and why."""

    print(col("  DECISION:", C.BOLD + C.WHITE))

    if not matched_rule:
        print(f"    Rule:   {col('No matching rule found', C.YELLOW)}")
        print(f"    Action: {col('SKIP — no action taken', C.DIM)}")
        print()
        return

    print(f"    Rule:   {col(matched_rule.rule_name, C.CYAN)}")
    print(f"    Action: {col(matched_rule.action, C.WHITE + C.BOLD)}")

    if safety:
        checks = []
        for reason in safety.reasons:
            if reason == "dry_run_active":
                checks.append(col("DRY-RUN", C.YELLOW))
            elif reason == "confidence_ok":
                checks.append(col("Confidence OK", C.GREEN))
            elif reason == "confidence_too_low":
                checks.append(col("Low Confidence", C.RED))
            elif reason == "rate_limit_ok":
                checks.append(col("Rate OK", C.GREEN))
            elif reason == "rate_limit_exceeded":
                checks.append(col("Rate Limited", C.RED))

        print(f"    Safety: {' | '.join(checks)}")

        if safety.warnings:
            for w in safety.warnings:
                print(f"    {col(f'Warning: {w}', C.YELLOW)}")
    print()


def show_reply_being_sent(
    original_email: EmailData,
    reply_text: str,
    is_sending: bool,
    dry_run: bool,
):
    """
    Show the reply prominently — this is what the agent is sending.
    This is the MOST IMPORTANT display in the whole app.
    """
    from src.clients.gmail_client import GmailClient

    to_addr = GmailClient.extract_email_address(original_email.from_address)
    reply_subject = GmailClient.make_reply_subject(original_email.subject)

    if is_sending and not dry_run:
        header_color = C.GREEN + C.BOLD
        header_text = "SENDING REPLY"
        header_icon = ">>"
    elif dry_run:
        header_color = C.YELLOW + C.BOLD
        header_text = "REPLY DRAFT (DRY RUN - NOT SENDING)"
        header_icon = "**"
    else:
        header_color = C.BLUE + C.BOLD
        header_text = "REPLY DRAFT (Saved for human review)"
        header_icon = "--"

    print(col(f"  {header_icon} {header_text} {header_icon}", header_color))
    print(col(f"  +{'=' * 56}+", header_color))
    print(col(f"  |", header_color) + f" To:      {col(to_addr, C.CYAN)}")
    print(col(f"  |", header_color) + f" Subject: {reply_subject}")
    print(col(f"  |", header_color) + f"{'─' * 50}")
    print(col(f"  |", header_color))

    # Show reply body
    for line in reply_text.split("\n"):
        # Handle long lines
        while len(line) > 52:
            print(col(f"  |", header_color) + f"  {line[:52]}")
            line = line[52:]
        print(col(f"  |", header_color) + f"  {line}")

    print(col(f"  |", header_color))
    print(col(f"  +{'=' * 56}+", header_color))
    print()


def show_send_result(success: bool, to_address: str):
    """Show whether the email was actually sent."""
    if success:
        print(col(f"  [SENT] Reply delivered to {to_address}", C.GREEN + C.BOLD))
    else:
        print(col(f"  [FAILED] Could not send reply to {to_address}", C.RED + C.BOLD))
    print()


def show_action_result(action: str, dry_run: bool):
    """Show the final action taken for non-reply actions."""

    results = {
        "ignored": {
            "icon": "IGNORED",
            "desc": "Spam/junk email - no action taken",
            "color": C.DIM,
        },
        "archived": {
            "icon": "ARCHIVED",
            "desc": "Newsletter moved to archive",
            "color": C.CYAN,
        },
        "flagged": {
            "icon": "FLAGGED",
            "desc": "Marked for human attention",
            "color": C.YELLOW,
        },
        "flagged_and_drafted": {
            "icon": "FLAGGED + DRAFTED",
            "desc": "Flagged for attention, reply draft created",
            "color": C.YELLOW,
        },
        "draft_saved": {
            "icon": "DRAFT SAVED",
            "desc": "Reply draft saved for human review",
            "color": C.BLUE,
        },
        "reply_sent": {
            "icon": "REPLY SENT",
            "desc": "Automated reply sent successfully",
            "color": C.GREEN,
        },
        "skipped": {
            "icon": "SKIPPED",
            "desc": "No matching rule, no action taken",
            "color": C.DIM,
        },
        "error": {
            "icon": "ERROR",
            "desc": "An error occurred during processing",
            "color": C.RED,
        },
    }

    info = results.get(action, {"icon": action, "desc": "", "color": C.WHITE})

    if dry_run and action not in ("skipped", "error", "ignored"):
        print(f"  {col('[' + info['icon'] + ']', info['color'])} {info['desc']}")
        print(f"  {col('(DRY RUN - no actual action performed)', C.YELLOW)}")
    else:
        print(f"  {col('[' + info['icon'] + ']', info['color'])} {info['desc']}")
    print()


def show_processing_error(email_data: EmailData, error_msg: str):
    """Show error during processing."""
    print(col(f"  [ERROR] Failed to process this email", C.RED + C.BOLD))
    print(f"    From:  {email_data.from_address}")
    print(f"    Error: {error_msg}")
    print(f"    {col('Skipping to next email...', C.DIM)}")
    print()


def show_email_count(count: int):
    """Show number of emails found."""
    if count == 0:
        print(col("  No unread emails found. Inbox is clean!", C.GREEN))
    else:
        print(
            f"  Found {col(str(count), C.WHITE + C.BOLD)} unread email(s) to process."
        )
    print()


# ──────────────────────────────────────────────
# FINAL SUMMARY
# ──────────────────────────────────────────────


def show_run_summary(results: list, dry_run: bool):
    """Show comprehensive run summary."""

    # Count actions
    action_counts = {}
    errors = 0
    classifications = {}

    for result in results:
        action = result.action_taken
        action_counts[action] = action_counts.get(action, 0) + 1
        if not result.success:
            errors += 1
        if result.classification:
            intent = result.classification.intent
            classifications[intent] = classifications.get(intent, 0) + 1

    mode = (
        col("LIVE MODE", C.RED + C.BOLD)
        if not dry_run
        else col("DRY RUN", C.YELLOW + C.BOLD)
    )

    print()
    print(col("+" + "=" * 58 + "+", C.CYAN))
    print(
        col("|", C.CYAN)
        + col("                    RUN SUMMARY                         ", C.BOLD)
        + col("|", C.CYAN)
    )
    print(col("+" + "=" * 58 + "+", C.CYAN))
    print()
    print(f"  Mode:       {mode}")
    print(f"  Processed:  {len(results)} email(s)")
    print(f"  Time:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Classification breakdown
    if classifications:
        print(col("  What was in the inbox:", C.BOLD))
        for intent, count in sorted(classifications.items(), key=lambda x: -x[1]):
            bar = "#" * count
            print(f"    {intent:<20} {bar} ({count})")
        print()

    # Action breakdown
    print(col("  What the agent did:", C.BOLD))

    action_display = {
        "reply_sent": ("Replies sent", C.GREEN),
        "draft_saved": ("Drafts saved", C.BLUE),
        "flagged_and_drafted": ("Flagged + Drafted", C.YELLOW),
        "archived": ("Archived", C.CYAN),
        "flagged": ("Flagged", C.YELLOW),
        "ignored": ("Ignored (spam)", C.DIM),
        "skipped": ("Skipped (no rule)", C.DIM),
        "error": ("Errors", C.RED),
    }

    for action_key, (label, color) in action_display.items():
        count = action_counts.get(action_key, 0)
        if count > 0:
            print(f"    {col(label + ':', color):<40} {count}")

    if errors > 0:
        print()
        print(col(f"  WARNING: {errors} error(s) occurred during processing", C.RED))

    print()
    print(col("+" + "=" * 58 + "+", C.CYAN))

    # Per-email summary table
    print()
    print(col("  Per-Email Results:", C.BOLD))
    print(f"  {'#':<3} {'From':<25} {'Intent':<18} {'Conf':<6} {'Action'}")
    print(f"  {'--':<3} {'---':<25} {'---':<18} {'---':<6} {'---'}")

    for i, result in enumerate(results, 1):
        from_addr = result.email.from_address[:24]

        if result.classification:
            intent = result.classification.intent
            conf = f"{result.classification.confidence:.0%}"
        else:
            intent = "N/A"
            conf = "N/A"

        action = result.action_taken

        # Color code the action
        action_colors = {
            "reply_sent": C.GREEN,
            "draft_saved": C.BLUE,
            "flagged_and_drafted": C.YELLOW,
            "archived": C.CYAN,
            "flagged": C.YELLOW,
            "ignored": C.DIM,
            "skipped": C.DIM,
            "error": C.RED,
        }
        a_color = action_colors.get(action, C.WHITE)

        print(f"  {i:<3} {from_addr:<25} {intent:<18} {conf:<6} {col(action, a_color)}")

    print()
