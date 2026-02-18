# Email Automation Agent

An AI-powered email agent that autonomously processes Gmail emails using 
Google Gemini 2.5 Flash for classification and response generation.

## What It Does

The agent connects to your Gmail inbox, reads unread emails, and for each one:
1. **Classifies** the email (intent, priority, confidence) using Gemini AI
2. **Extracts entities** (dates, names, action items)
3. **Matches rules** you define in config to determine what to do
4. **Runs safety checks** (confidence threshold, rate limits, dry-run)
5. **Takes action** (auto-reply, archive, flag, ignore, or save draft)
6. **Logs everything** for audit trail

## Quick Start

### Prerequisites
- Python 3.9+
- Gmail account with 2FA enabled
- Google Gemini API key

### Setup

1. **Clone and install dependencies**
   ```bash
   git clone <repo-url>
   cd email-agent
   pip install -r requirements.txt
   Gmail App Password

Enable 2FA on your Gmail account
Go to Google Account > Security > App Passwords
Generate an app password for "Mail"
Gemini API Key

Go to https://aistudio.google.com/
Create an API key
Configure credentials

bash
cp .env.example .env
# Edit .env with your credentials
Configure rules

bash
cp config/config.example.yaml config/config.yaml
# Edit rules as needed
Run the agent

bash
python src/main.py                          # Default config
python src/main.py --config custom.yaml     # Custom config
Configuration
Environment Variables (.env)
text
GMAIL_EMAIL=your-email@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
GEMINI_API_KEY=your-api-key
DRY_RUN=true                                   # Set to false for live mode
Rules (config.yaml)
Rules are processed in order. First match wins.

yaml
rules:
  - name: "Spam Detection"
    conditions:
      intent: "spam"
    action: "ignore"

  - name: "Meeting Auto-Reply"
    conditions:
      intent: "meeting_request"
    action: "reply"
    auto_send: true

  - name: "VIP Sender"
    conditions:
      intent: "general_inquiry"
      sender_contains: "@important-client.com"
    action: "flag"
Supported Conditions
Condition	Description	Example
intent	Exact match on AI classification	"spam"
priority	Exact match on priority	"high"
confidence_min	Minimum confidence score	0.85
sender_contains	Substring match on sender	"@company.com"
subject_contains	Substring match on subject	"urgent"
Supported Actions
Action	Description	Sends Email?
ignore	Do nothing	No
archive	Mark as read	No
flag	Flag for human attention	No
reply	Generate and send reply	Yes (if auto_send)
draft_reply	Generate reply, save as draft	No
flag_and_draft	Flag + generate draft	No
Safety Parameters
yaml
safety:
  dry_run: true              # Log only, take no actions
  confidence_threshold: 0.85 # Below this = needs human review
  max_sends_per_hour: 20     # Rate limit for outgoing emails
Architecture
See docs/architecture.md for detailed architecture.

text
Email Received
    |
    v
[Gmail Client] -- IMAP --> Fetch unread emails
    |
    v
[Gemini Agent] -- API --> Classify intent, extract entities
    |
    v
[Rule Engine] -- Config --> Match classification to rules
    |
    v
[Safety Module] -- Checks --> Confidence, rate limit, dry-run
    |
    v
[Action Executor] -- SMTP --> Send reply / archive / flag / ignore
    |
    v
[Audit Logger] -- File --> Log all decisions as JSON
Project Structure
text
email-agent/
├── src/
│   ├── main.py              # Orchestrator and entry point
│   ├── gmail_client.py      # IMAP/SMTP email operations
│   ├── gemini_agent.py      # AI classification and reply generation
│   ├── rule_engine.py       # Rule matching logic
│   ├── safety.py            # Safety checks and rate limiting
│   ├── config_manager.py    # Configuration loading and validation
│   ├── models.py            # Data structures
│   ├── display.py           # Console output formatting
│   └── audit_logger.py      # Structured JSON logging
├── config/
│   ├── config.yaml          # Main configuration
│   └── config.example.yaml  # Example configuration
├── tests/
│   ├── test_rule_engine.py  # Rule engine unit tests
│   ├── test_safety.py       # Safety module unit tests
│   └── send_test_emails.py  # Test email sender utility
├── logs/                    # Audit logs (created at runtime)
├── docs/
│   ├── architecture.md
│   ├── prompt_engineering.md
│   └── design_decisions.md
├── .env.example
├── requirements.txt
└── README.md
Testing
bash
# Unit tests
python -m pytest tests/ -v

# Send test emails to your agent
python tests/send_test_emails.py

# Run agent
python src/main.py
Design Decisions
See docs/design_decisions.md for full details.

Key tradeoffs:

IMAP/SMTP over Gmail API: Required by spec. In production, OAuth2 would be better.
Safe by default: dry_run=true, auto_send=false unless explicitly configured.
First-match-wins rules: Simple, predictable. More specific rules go first.
15s API delay: Respects Gemini free tier limits (5 RPM, 20 RPD).
Fallback classification: If AI fails, returns 0.0 confidence so safety blocks all actions.
text

---

### 5. Architecture Doc

### File: `docs/architecture.md`

```markdown
# Architecture Overview

## System Design

The agent follows a linear pipeline architecture:
Config (.env + YAML)
|
v
[Main Orchestrator]
|
+---------+-----------+-----------+---------+
| | | | |
Gmail Gemini Rule Safety Audit
Client Agent Engine Module Logger

text

## Data Flow

Every email flows through the same pipeline:

1. **Gmail Client** fetches unread emails via IMAP, parses them into `EmailData` objects
2. **Gemini Agent** classifies each email, returning `ClassificationResult` with intent, priority, confidence, entities
3. **Rule Engine** matches the classification against configured rules, returning `MatchedRule` with action
4. **Safety Module** evaluates whether the action is safe to execute, returning `SafetyDecision`
5. **Main Orchestrator** executes the action (send, archive, flag, ignore) or saves as draft
6. **Audit Logger** records the complete decision chain as structured JSON

## Module Responsibilities

| Module | Responsibility | Dependencies |
|--------|---------------|-------------|
| `models.py` | Data structures | None |
| `config_manager.py` | Load and validate config | models |
| `gmail_client.py` | Email read/send/archive | models |
| `gemini_agent.py` | AI classification + reply | models |
| `rule_engine.py` | Rule pattern matching | models |
| `safety.py` | Safety gates | models |
| `display.py` | Console formatting | models |
| `audit_logger.py` | JSON file logging | models |
| `main.py` | Orchestration | All above |

## Key Design Principle

Modules communicate only through shared data models. No module imports another module (except main.py which imports all). This enables independent testing and clear separation of concerns.

## Error Handling Strategy

- One failed email never crashes the entire agent
- API failures return fallback classification with 0.0 confidence
- Safety module blocks all actions when confidence is 0.0
- All errors are logged with full context
- Connections are always closed in finally blocks
6. Prompt Engineering Doc
File: docs/prompt_engineering.md
markdown
