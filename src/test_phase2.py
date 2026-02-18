# src/test_phase4.py
# Test the Gemini agent with real API calls
# Delete after verification

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config_manager import ConfigManager
from src.gemini_agent import GeminiAgent
from src.models import EmailData

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

# ──────────────────────────────────────────────
# SAMPLE TEST EMAILS
# ──────────────────────────────────────────────

SAMPLE_EMAILS = {
    "meeting_request": EmailData(
        id="1",
        from_address="John Smith <john@company.com>",
        to_address="agent@gmail.com",
        subject="Can we sync this Friday?",
        body="""Hey,

I'd like to discuss the Q3 product roadmap with you. 
Are you free this Friday at 3pm? We could do a 30-minute call.

Let me know what works.

Best,
John""",
        date="2025-06-14 09:00:00",
        message_id="<meeting123@mail.com>",
    ),

    "newsletter": EmailData(
        id="2",
        from_address="deals@megastore.com",
        to_address="agent@gmail.com",
        subject="🔥 MEGA SALE - 70% OFF EVERYTHING THIS WEEKEND!!!",
        body="""Don't miss our biggest sale of the year!

Shop now and save up to 70% on all products.
Free shipping on orders over \$50.

Use code: MEGA70 at checkout.

This offer expires Sunday midnight.

Unsubscribe: click here
""",
        date="2025-06-14 06:00:00",
        message_id="<newsletter456@megastore.com>",
    ),

    "urgent_issue": EmailData(
        id="3",
        from_address="Sarah Chen <sarah@client.com>",
        to_address="agent@gmail.com",
        subject="URGENT: Production API returning 500 errors",
        body="""Hi,

Our production environment started throwing 500 errors about 15 minutes ago. 
Multiple customers are reporting they can't access the dashboard.

The error seems to be coming from the /api/v2/users endpoint.
Our monitoring shows error rate jumped from 0.1% to 45%.

This is affecting approximately 2,000 active users right now.
Please investigate ASAP.

Thanks,
Sarah Chen
VP of Engineering, ClientCorp
""",
        date="2025-06-14 10:30:00",
        message_id="<urgent789@client.com>",
    ),

    "spam": EmailData(
        id="4",
        from_address="winner@lottery-prize.xyz",
        to_address="agent@gmail.com",
        subject="Congratulations!!! You've WON \$5,000,000!!!",
        body="""CONGRATULATIONS!!!

You have been selected as the WINNER of our international lottery!
You have won \$5,000,000 USD!!!

To claim your prize, simply reply with:
- Your full name
- Bank account number
- Social security number

Act NOW! This offer expires in 24 hours!

Dr. James Williams
International Lottery Commission
""",
        date="2025-06-14 03:00:00",
        message_id="<spam000@lottery.xyz>",
    ),

    "general_inquiry": EmailData(
        id="5",
        from_address="Maria Garcia <maria@partner.com>",
        to_address="agent@gmail.com",
        subject="Question about API documentation",
        body="""Hi there,

I've been going through your API docs and had a quick question.

Is there a rate limit on the /search endpoint? I couldn't find 
it mentioned in the documentation. We're planning to integrate 
it into our product and expect about 1000 requests per minute 
during peak hours.

Also, do you support webhook callbacks for async operations?

Thanks!
Maria
""",
        date="2025-06-14 11:00:00",
        message_id="<inquiry101@partner.com>",
    ),
}


def test_connection():
    """Test 1: Can we connect to Gemini?"""
    print("\n" + "=" * 60)
    print("TEST 1: Gemini API Connection")
    print("=" * 60)

    config = ConfigManager().load()
    agent = GeminiAgent(config.gemini)

    success = agent.test_connection()
    return success


def test_classification():
    """Test 2: Classify all sample emails."""
    print("\n" + "=" * 60)
    print("TEST 2: Email Classification")
    print("=" * 60)

    config = ConfigManager().load()
    agent = GeminiAgent(config.gemini)

    results = {}

    for email_type, email_data in SAMPLE_EMAILS.items():
        print(f"\n{'─' * 60}")
        print(f"📧 Testing: {email_type}")
        print(f"   Subject: {email_data.subject}")
        print(f"{'─' * 60}")

        classification = agent.classify_email(email_data)

        # Check if classification matches expected type
        match = "✅" if classification.intent == email_type else "⚠️"

        print(f"\n   {match} Intent:      {classification.intent}")
        print(f"   Priority:    {classification.priority}")
        print(f"   Confidence:  {classification.confidence}")
        print(f"   Entities:    {classification.entities}")
        print(f"   Action:      {classification.suggested_action}")
        print(f"   Reasoning:   {classification.reasoning}")

        results[email_type] = {
            "expected": email_type,
            "got": classification.intent,
            "confidence": classification.confidence,
            "correct": classification.intent == email_type,
        }

    # Print summary
    print(f"\n{'=' * 60}")
    print("CLASSIFICATION SUMMARY")
    print(f"{'=' * 60}")

    correct = sum(1 for r in results.values() if r["correct"])
    total = len(results)

    for email_type, result in results.items():
        status = "✅" if result["correct"] else "❌"
        print(f"  {status} {email_type:20s} -> {result['got']:20s} (confidence: {result['confidence']:.2f})")

    print(f"\n  Accuracy: {correct}/{total} ({100 * correct / total:.0f}%)")

    return correct == total


def test_reply_generation():
    """Test 3: Generate replies for different email types."""
    print("\n" + "=" * 60)
    print("TEST 3: Reply Generation")
    print("=" * 60)

    config = ConfigManager().load()
    agent = GeminiAgent(config.gemini)

    # Only generate replies for email types that need replies
    reply_types = ["meeting_request", "urgent_issue", "general_inquiry"]

    for email_type in reply_types:
        email_data = SAMPLE_EMAILS[email_type]

        print(f"\n{'─' * 60}")
        print(f"📧 Generating reply for: {email_type}")
        print(f"   Original subject: {email_data.subject}")
        print(f"{'─' * 60}")

        # First classify
        classification = agent.classify_email(email_data)

        # Then generate reply
        reply = agent.generate_reply(email_data, classification)

        if reply:
            print(f"\n   ✅ Generated Reply:")
            print(f"   ┌{'─' * 50}┐")
            for line in reply.split("\n"):
                print(f"   │ {line:48s} │")
            print(f"   └{'─' * 50}┘")
        else:
            print(f"\n   ❌ Failed to generate reply")


def test_edge_cases():
    """Test 4: Handle edge cases gracefully."""
    print("\n" + "=" * 60)
    print("TEST 4: Edge Cases")
    print("=" * 60)

    config = ConfigManager().load()
    agent = GeminiAgent(config.gemini)

    # Edge case 1: Empty body email
    print(f"\n{'─' * 60}")
    print("Edge case 1: Empty body email")
    empty_email = EmailData(
        id="edge1",
        from_address="someone@test.com",
        to_address="agent@gmail.com",
        subject="(no subject)",
        body="",
        date="2025-06-14",
    )
    result = agent.classify_email(empty_email)
    print(f"  Intent: {result.intent}, Confidence: {result.confidence}")
    print(f"  ✅ Handled without crashing")

    # Edge case 2: Very long email
    print(f"\n{'─' * 60}")
    print("Edge case 2: Very long email (truncated to 2000 chars)")
    long_email = EmailData(
        id="edge2",
        from_address="verbose@test.com",
        to_address="agent@gmail.com",
        subject="Very detailed proposal",
        body="This is a very detailed proposal. " * 500,
        date="2025-06-14",
    )
    result = agent.classify_email(long_email)
    print(f"  Intent: {result.intent}, Confidence: {result.confidence}")
    print(f"  ✅ Handled without crashing")

    # Edge case 3: Non-English email
    print(f"\n{'─' * 60}")
    print("Edge case 3: Non-English email")
    foreign_email = EmailData(
        id="edge3",
        from_address="pierre@company.fr",
        to_address="agent@gmail.com",
        subject="Réunion vendredi",
        body="Bonjour, pouvons-nous planifier une réunion vendredi à 14h? Merci, Pierre",
        date="2025-06-14",
    )
    result = agent.classify_email(foreign_email)
    print(f"  Intent: {result.intent}, Confidence: {result.confidence}")
    print(f"  ✅ Handled without crashing")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║         Gemini Agent — Phase 4 Tests                ║")
    print("╚══════════════════════════════════════════════════════╝")

    # Test 1: Connection
    if not test_connection():
        print("\n❌ Gemini connection failed. Check API key.")
        sys.exit(1)

    # Test 2: Classification
    test_classification()

    # Test 3: Reply generation
    test_reply_generation()

    # Test 4: Edge cases
    test_edge_cases()

    print(f"\n{'=' * 60}")
    print("Phase 4 testing complete!")
    print(f"{'=' * 60}")