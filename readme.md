#  Email Automation Agent

AI-powered Gmail automation agent that classifies emails and takes actions automatically using **Google Gemini 2.5 Flash**.

It safely processes unread emails, applies rule-based logic, and performs controlled actions like replying, flagging, archiving, or drafting responses.

---

https://github.com/user-attachments/assets/f13a4555-a32a-457a-982b-6198d4c3b204


##  Features

-  AI Email Classification (intent, priority, confidence)
-  Entity Extraction (dates, names, action items)
-  Rule-Based Action Engine (first match wins)
-  Safety Layer (confidence threshold, rate limits, dry-run mode)
-  Auto Reply / Draft / Flag / Archive
-  Structured JSON Audit Logging
-  Unit-Tested Rule & Safety Modules

---

## Architecture Overview

```
Email Received
      ↓
[Gmail Client]  → Fetch unread emails (IMAP)
      ↓
[Gemini Agent]  → Classify + extract entities
      ↓
[Rule Engine]   → Match against config rules
      ↓
[Safety Module] → Confidence + rate limit checks
      ↓
[Action Executor] → Reply / Draft / Flag / Archive
      ↓
[Audit Logger]  → Structured JSON log
```

**Design Principle:**  
Modules communicate only via shared data models.  
Each module is independently testable.

---

##  Project Structure

```
email-agent/
│
├── src/
│   ├── main.py
│   ├── gmail_client.py
│   ├── gemini_agent.py
│   ├── rule_engine.py
│   ├── safety.py
│   ├── config_manager.py
│   ├── models.py
│   ├── display.py
│   └── audit_logger.py
│
├── config/
│   ├── config.yaml
│   └── config.example.yaml
│
├── tests/
├── docs/
├── logs/
├── .env.example
└── requirements.txt
```

---

#  Quick Start

## 1️⃣ Prerequisites

- Python **3.9+**
- Gmail account (2FA enabled)
- Google Gemini API key

---

## 2️⃣ Installation

```bash
git clone <repo-url>
cd email-agent
pip install -r requirements.txt
```

---

## 3️⃣ Gmail Setup (App Password)

1. Enable **2-Factor Authentication** on Gmail  
2. Go to:  
   `Google Account → Security → App Passwords`  
3. Generate App Password for **Mail**  
4. Copy it for `.env`

---

## 4️⃣ Gemini API Key

1. Go to https://aistudio.google.com/  
2. Create API Key  
3. Copy it  

---

## 5️⃣ Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```
GMAIL_EMAIL=your-email@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
GEMINI_API_KEY=your-api-key
DRY_RUN=true
```

⚠️ Keep `DRY_RUN=true` for safe testing. and false if you want that agent can send emails and save draft messages and all 

---

## 6️⃣ Configure Rules

```bash
cp config/config.example.yaml config/config.yaml
```

Example rule:

```yaml
rules:
  - name: "Spam Detection"
    conditions:
      intent: "spam"
    action: "ignore"

  - name: "Meeting Auto Reply"
    conditions:
      intent: "meeting_request"
    action: "reply"
    auto_send: true
```

### Supported Conditions

- `intent`
- `priority`
- `confidence_min`
- `sender_contains`
- `subject_contains`

### Supported Actions

- `ignore`
- `archive`
- `flag`
- `reply`
- `draft_reply`
- `flag_and_draft`

---

#  Safety Configuration

```yaml
safety:
  dry_run: true
  confidence_threshold: 0.85
  max_sends_per_hour: 20
```

**Safety Guarantees:**

- Low-confidence emails never auto-send
- Rate-limited outgoing emails
- Dry-run mode logs only (no real actions)

---

# ▶️ Run the Agent

Default config:

```bash
python src/main.py
```

Custom config:

```bash
python src/main.py --config config/custom.yaml
```

---

#  Testing

Run unit tests:

```bash
python -m pytest tests/ -v
```



#  Design Principles

- Safe by default (`dry_run=true`)
- First-match-wins rule engine
- Modular architecture
- Clear audit trail
- Fail-safe fallback (0.0 confidence blocks actions)

---


