# tests/send_test_emails.py

"""
Sends 6 carefully crafted test emails to the agent.
Each email is realistic, detailed, and tests a different classification.

Usage:
    python tests/send_test_emails.py          # Send all 6
    python tests/send_test_emails.py list     # Show all emails
    python tests/send_test_emails.py send 3   # Send one by ID
"""

import smtplib
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ──────────────────────────────────────────────
# CONFIGURE THESE
# ──────────────────────────────────────────────

SENDER_EMAIL = "aryakumari3953@gmail.com"  # Change this
SENDER_APP_PASSWORD = "wbxw qznk sube xmbg"  # Change this
RECIPIENT_EMAIL = "augmenttest3@gmail.com"

# ──────────────────────────────────────────────
# 6 TEST EMAILS — Each tests a different scenario
# ──────────────────────────────────────────────

TEST_EMAILS = [
    # ──────────────────────────────────────────
    # EMAIL 1: MEETING REQUEST
    # Expected: meeting_request, medium priority
    # Should: auto-reply (if auto_send=true)
    # Entities: Friday June 20, 2:30pm, John, Sarah
    # ──────────────────────────────────────────
    {
        "id": 1,
        "category": "Meeting Request",
        "from_name": "John Mitchell",
        "subject": "Product Roadmap Discussion - Can we meet Friday?",
        "body": """Hi there,

Hope you're doing well! I wanted to reach out about scheduling a meeting to go over our Q3 product roadmap. There are several items I'd like to align on before we present to the leadership team next month.

Specifically, I'd like to discuss:
- The new authentication module timeline (currently slated for July)
- API v3 migration plan and customer communication strategy  
- Resource allocation for the mobile team in Q3
- Budget review for the cloud infrastructure upgrade

Would Friday, June 20th at 2:30 PM work for you? I was thinking we could do a 45-minute video call. Sarah from the design team will also be joining to walk us through the updated mockups.

If Friday doesn't work, I'm also open on Monday morning or Tuesday after 3 PM. Just let me know what fits your schedule best.

Looking forward to connecting!

Best regards,
John Mitchell
Director of Product, TechVentures Inc.
john.mitchell@techventures.com
+1 (415) 555-0187""",
    },
    # ──────────────────────────────────────────
    # EMAIL 2: NEWSLETTER / PROMOTIONAL
    # Expected: newsletter, low priority
    # Should: auto-archive
    # ──────────────────────────────────────────
    {
        "id": 2,
        "category": "Newsletter / Promotional",
        "from_name": "CloudStack Weekly",
        "subject": "CloudStack Weekly #147: Kubernetes 2.0 Released, AWS Price Cuts, and More",
        "body": """CloudStack Weekly - Issue #147
Your weekly dose of cloud computing news and insights.
June 14, 2025

---------------------------------------------
TOP STORIES THIS WEEK
---------------------------------------------

1. Kubernetes 2.0 Officially Released
   The long-awaited Kubernetes 2.0 has finally landed with major improvements to pod scheduling, native support for WebAssembly workloads, and a completely redesigned dashboard. Migration guides are available at kubernetes.io/v2-migration.

2. AWS Announces 30% Price Reduction on EC2 Instances
   Starting July 1st, AWS is cutting prices across all EC2 instance families. The largest cuts are in the compute-optimized C7 series. This puts additional pressure on Azure and GCP to follow suit.

3. The Rise of Edge Computing: What You Need to Know
   Our deep-dive analysis into edge computing trends shows a 340% increase in edge deployments over the past 18 months. Financial services and healthcare are leading adoption.

4. Tutorial: Building Serverless APIs with Rust and AWS Lambda
   Step-by-step guide to deploying high-performance serverless functions using Rust. Includes benchmarks showing 10x improvement over Node.js cold starts.

---------------------------------------------
COMMUNITY SPOTLIGHT
---------------------------------------------
This week we feature an open-source project from our community: CloudCost - a real-time cloud spending dashboard that works across AWS, Azure, and GCP.
Star it on GitHub: github.com/cloudcost/dashboard

---------------------------------------------
You're receiving this because you subscribed at cloudstackweekly.com
Unsubscribe | View Online | Preferences

CloudStack Media Inc. | 123 Tech Blvd, San Francisco, CA 94105""",
    },
    # ──────────────────────────────────────────
    # EMAIL 3: URGENT ISSUE
    # Expected: urgent_issue, high priority
    # Should: flag + draft reply (NOT auto-send)
    # Entities: 2:47 AM, db-primary-01, 15000 users
    # ──────────────────────────────────────────
    {
        "id": 3,
        "category": "Urgent Issue",
        "from_name": "Sarah Kim",
        "subject": "CRITICAL: Database failover triggered - customer data access disrupted",
        "body": """Hi Team,

This is an urgent escalation. At approximately 2:47 AM EST today, our primary database cluster (db-primary-01) experienced an unexpected failover event. The automatic failover to the secondary node completed, but we are seeing significant issues:

CURRENT IMPACT:
- Approximately 15,000 active users are experiencing intermittent 503 errors
- The customer dashboard is loading with 8-12 second delays (normal is under 500ms)
- Our payment processing queue has backed up with approximately 2,300 pending transactions
- Three enterprise clients (Acme Corp, GlobalTech, and MedStar) have already opened P1 support tickets

ROOT CAUSE (preliminary):
Our initial investigation suggests a disk I/O saturation event on the primary node. The monitoring dashboard shows disk utilization spiked to 100% at 2:45 AM, two minutes before the failover. We suspect this may be related to the batch job optimization we deployed yesterday evening (deploy #4521).

IMMEDIATE ACTIONS NEEDED:
1. Roll back deploy #4521 on the secondary node before it triggers the same issue
2. Scale up the read replicas to handle the current query load
3. Manually process the backed-up payment transactions to prevent SLA breaches
4. Communicate status to the three enterprise clients within the next 30 minutes

War room is active here: https://meet.internal.com/incident-0618
Incident Slack channel: #incident-db-failover-0618

Please join immediately if you are available. We need all hands on deck.

Sarah Kim
Senior Site Reliability Engineer
Platform Infrastructure Team
Pager: +1 (555) 911-0042""",
    },
    # ──────────────────────────────────────────
    # EMAIL 4: SPAM / PHISHING
    # Expected: spam, low priority
    # Should: ignore completely
    # ──────────────────────────────────────────
    {
        "id": 4,
        "category": "Spam / Phishing",
        "from_name": "Account Security Department",
        "subject": "Important: Unusual sign-in activity detected on your account - Action Required",
        "body": """Dear Valued Account Holder,

Our advanced security monitoring system has detected unusual sign-in activity associated with your account. For your protection, we have temporarily limited some account features until you verify your identity.

SUSPICIOUS ACTIVITY DETECTED:
- Location: Minsk, Belarus (IP: 185.234.72.xxx)
- Time: June 14, 2025 at 03:22 AM
- Device: Unknown Linux Device
- Action: Attempted to change account password and recovery email

To prevent unauthorized access and restore full account functionality, you must verify your identity within 24 hours by clicking the secure link below:

>>> VERIFY YOUR IDENTITY NOW <<<
http://security-verification-portal.account-protect.xyz/verify?user=target&token=a8f2k4

If you do not complete verification within 24 hours:
- Your account will be permanently suspended
- All associated data will be deleted
- You will lose access to all connected services

For additional assistance, contact our 24/7 security helpline:
Phone: +1 (800) 555-0000
Email: support@account-protect.xyz

Remember: We will never ask for your password directly. This automated message is sent from our secure notification system.

Sincerely,
The Account Security Department
Global Digital Security Division

---
This message is confidential and intended solely for the addressee.
Copyright 2025 Secure Account Services LLC. All rights reserved.
Ref: SEC-2025-061425-AX7""",
    },
    # ──────────────────────────────────────────
    # EMAIL 5: GENERAL INQUIRY
    # Expected: general_inquiry, medium priority
    # Should: auto-reply (if auto_send=true)
    # Entities: Maria, PartnerTech, /search, /analytics
    # ──────────────────────────────────────────
    {
        "id": 5,
        "category": "General Inquiry",
        "from_name": "Maria Santos",
        "subject": "API Integration Questions - Webhook Support and Rate Limits",
        "body": """Hello,

My name is Maria Santos and I'm a Senior Backend Engineer at PartnerTech Solutions. We're currently evaluating your platform for integration into our enterprise product suite and I had several technical questions I was hoping you could help clarify.

1. RATE LIMITS
   We anticipate our integration will generate approximately 2,000-3,000 API requests per minute during peak business hours (9 AM - 5 PM EST). Your documentation mentions a rate limit on the /search endpoint but doesn't specify the exact threshold. Could you confirm what the limits are for enterprise-tier accounts?

2. WEBHOOK SUPPORT
   We need real-time notifications for certain events (user creation, payment status changes, and document updates). Does your platform support webhook callbacks? If so, what is the retry policy for failed webhook deliveries?

3. AUTHENTICATION
   We currently use OAuth 2.0 with PKCE for our client applications. Does your API support this flow, or would we need to implement a different authentication method?

4. DATA RESIDENCY
   Several of our clients are in the EU and subject to GDPR requirements. Do you offer data residency options in EU regions? Specifically, we would need Frankfurt or Dublin data centers.

5. SANDBOX ENVIRONMENT
   Is there a sandbox or staging environment available for integration testing? We'd need at least 3 developer accounts with separate API keys for our QA process.

We're targeting a Q3 launch for this integration, so any information you can provide in the next week or so would be very helpful for our planning.

I'd also be happy to schedule a technical deep-dive call with your API team if that would be more efficient.

Thank you for your time!

Best regards,
Maria Santos
Senior Backend Engineer
PartnerTech Solutions
maria.santos@partnertech.io
+1 (650) 555-0234""",
    },
    # ──────────────────────────────────────────
    # EMAIL 6: COMPLAINT
    # Expected: complaint, high/medium priority
    # Should: flag for review (NOT auto-reply)
    # Entities: Robert, 3 years, Account #78234
    # ──────────────────────────────────────────
    {
        "id": 6,
        "category": "Complaint",
        "from_name": "Robert Chen",
        "subject": "Ongoing Issues with Platform Stability - Considering Alternatives",
        "body": """To whom it may concern,

I am writing to formally document my growing frustration with the reliability of your platform. As a paying customer for the past three years on the Business Pro plan (Account #78234), I have watched the service quality deteriorate significantly over the past two quarters.

Here is a summary of the issues we've experienced just this month alone:

June 3rd: The reporting dashboard was completely unavailable for 6 hours during our end-of-quarter analysis. We had to manually compile reports for our board presentation, costing our team approximately 12 person-hours of unplanned work.

June 7th: Export functionality produced corrupted CSV files for datasets over 10,000 rows. We submitted ticket #SUP-45721 and received a response 72 hours later saying it was a "known issue." No ETA for a fix was provided.

June 11th: Our team experienced four separate instances of the application freezing during live client demonstrations. This was professionally embarrassing and damaged our credibility with a potential enterprise client worth approximately \$200K in annual revenue.

June 14th: The API started returning 429 (rate limit) errors despite our usage being well within our plan's documented limits. After spending 45 minutes with your support chatbot, I was told to "try again later."

What concerns me most is not just the technical issues themselves, but the pattern of inadequate support responses. When we do get a human response, it often comes 48-72 hours later with generic troubleshooting steps that don't address our specific situation.

I want to be clear: we have been loyal customers and have recommended your platform to several peers in our industry. However, I am now actively evaluating alternative solutions including CompetitorX and PlatformY, both of which have offered us trial accounts with dedicated support contacts.

Before making a final decision, I would like:
1. A detailed incident report for each of the outages mentioned above
2. A concrete timeline for resolving the known export bug
3. A credit for this month's subscription given the extent of service disruptions
4. Assignment of a dedicated account manager for our account going forward

I would appreciate a response within 48 hours. If these concerns cannot be adequately addressed, we will begin our migration process by end of month.

Regards,
Robert Chen
VP of Operations, DataDriven Analytics
Account #78234
robert.chen@datadriven.co
+1 (212) 555-0891""",
    },
]


def send_all():
    """Send all test emails."""
    print()
    print(f"  Sending {len(TEST_EMAILS)} test emails")
    print(f"  From: {SENDER_EMAIL}")
    print(f"  To:   {RECIPIENT_EMAIL}")
    print()

    for e in TEST_EMAILS:
        print(f"    [{e['id']}] {e['category']:<25} {e['subject'][:45]}")
    print()

    confirm = input("  Send all? (y/n): ")
    if confirm.lower() != "y":
        print("  Cancelled.")
        return

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
    except Exception as e:
        print(f"\n  Failed to connect: {e}")
        return

    sent = 0
    for email_data in TEST_EMAILS:
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{email_data['from_name']} <{SENDER_EMAIL}>"
            msg["To"] = RECIPIENT_EMAIL
            msg["Subject"] = email_data["subject"]
            msg.attach(MIMEText(email_data["body"], "plain"))

            server.send_message(msg)
            sent += 1
            print(f"  Sent [{email_data['id']}] {email_data['category']}")
            time.sleep(2)  # Delay between sends
        except Exception as e:
            print(f"  Failed [{email_data['id']}]: {e}")

    server.quit()
    print(f"\n  Done! {sent}/{len(TEST_EMAILS)} sent.")
    print(f"  Wait 30 seconds, then run: python src/main.py")
    print()


def send_one(email_id: int):
    """Send one email by ID."""
    email_data = next((e for e in TEST_EMAILS if e["id"] == email_id), None)
    if not email_data:
        print(f"  No email with ID {email_id}")
        return

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        msg = MIMEMultipart()
        msg["From"] = f"{email_data['from_name']} <{SENDER_EMAIL}>"
        msg["To"] = RECIPIENT_EMAIL
        msg["Subject"] = email_data["subject"]
        msg.attach(MIMEText(email_data["body"], "plain"))
        server.send_message(msg)
        server.quit()
        print(f"  Sent [{email_id}] {email_data['category']}")
    except Exception as e:
        print(f"  Failed: {e}")


def show_list():
    """List all test emails with details."""
    print()
    print(f"  {'ID':<4} {'Category':<28} {'Subject'}")
    print(f"  {'--':<4} {'---':<28} {'---'}")
    for e in TEST_EMAILS:
        print(f"  {e['id']:<4} {e['category']:<28} {e['subject'][:45]}")

    print(f"\n  Total: {len(TEST_EMAILS)} emails")
    print(f"  Estimated API calls: ~9 (6 classify + 3 reply generation)")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        show_list()
    elif len(sys.argv) > 2 and sys.argv[1] == "send":
        send_one(int(sys.argv[2]))
    else:
        send_all()
