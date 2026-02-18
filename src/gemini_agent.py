# src/gemini_agent.py
import time  # ← Make sure this is imported

"""
Gemini AI Agent
Handles all interactions with Google Gemini 2.5 Flash.
- Email classification (intent, priority, confidence, entities)
- Reply generation (contextual, professional responses)

The quality of this module depends heavily on prompt engineering.
"""

import json
import logging
import time
from typing import Optional

import google.generativeai as genai

from src.models import EmailData, ClassificationResult
from src.config_manager import GeminiConfig


logger = logging.getLogger(__name__)


# In the __init__ method, add:


class GeminiAgent:
    """
    AI agent powered by Gemini 2.5 Flash.

    Responsibilities:
      - Classify emails (intent, priority, confidence, entities)
      - Generate contextual reply drafts

    Usage:
        agent = GeminiAgent(config.gemini)
        classification = agent.classify_email(email_data)
        reply = agent.generate_reply(email_data, classification)
    """

    def __init__(self, config: GeminiConfig):
        self.config = config
        self._setup_client()
        self._last_api_call = 0
        self._min_delay = 15  # 15 seconds between calls (safe for 5 RPM)
        self._call_count = 0

    def _rate_limit_wait(self):
        """Wait if needed to stay within Gemini free tier rate limits."""
        elapsed = time.time() - self._last_api_call
        if elapsed < self._min_delay and self._last_api_call > 0:
            wait_time = self._min_delay - elapsed
            logger.info(
                f"[RATE LIMIT] Waiting {wait_time:.0f}s before next API call..."
            )
            time.sleep(wait_time)
        self._last_api_call = time.time()
        self._call_count += 1
        logger.debug(f"API call #{self._call_count}")

    def _setup_client(self):
        """Initialize the Gemini client."""
        genai.configure(api_key=self.config.api_key)
        self.model = genai.GenerativeModel(
            model_name=self.config.model,
            generation_config=genai.GenerationConfig(
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
            ),
        )
        logger.debug(f"Gemini agent initialized with model: {self.config.model}")

    # ──────────────────────────────────────────────
    # EMAIL CLASSIFICATION
    # ──────────────────────────────────────────────

    def classify_email(self, email_data: EmailData) -> ClassificationResult:
        """
        Classify an email using Gemini.

        Args:
            email_data: The email to classify

        Returns:
            ClassificationResult with intent, priority, confidence, entities
        """
        prompt = self._build_classification_prompt(email_data)

        try:
            # Call Gemini API
            self._rate_limit_wait()
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            logger.debug(f"Gemini raw response: {raw_text[:200]}...")

            # Parse the JSON response
            classification = self._parse_classification_response(raw_text)
            return classification

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Gemini JSON response: {e}")
            # Retry once with a simpler prompt
            return self._retry_classification(email_data)

        except Exception as e:
            logger.error(f"Gemini classification failed: {e}")
            # Return a safe fallback — low confidence so safety module blocks action
            return self._fallback_classification(str(e))

    def _build_classification_prompt(self, email_data: EmailData) -> str:
        """
        Build the classification prompt.

        This is the MOST IMPORTANT function in the entire project.
        The quality of classification depends entirely on this prompt.
        """

        # Include thread context if available
        thread_context = ""
        if email_data.thread_messages:
            thread_context = "\nPREVIOUS MESSAGES IN THREAD:\n"
            for msg in email_data.thread_messages[-3:]:  # Last 3 messages max
                thread_context += f"  From: {msg.get('from', 'unknown')}\n"
                thread_context += f"  Body: {msg.get('body', '')[:200]}\n\n"

        prompt = f"""You are an expert email classification assistant. Your job is to analyze emails and return a structured classification.

TASK: Analyze the following email and classify it accurately.

EMAIL TO CLASSIFY:
  From: {email_data.from_address}
  To: {email_data.to_address}
  Subject: {email_data.subject}
  Date: {email_data.date}
  Body:
  {email_data.body[:2000]}
{thread_context}

CLASSIFICATION CATEGORIES (choose exactly one):
  - "meeting_request": Someone wants to schedule, reschedule, or discuss a meeting time
  - "newsletter": Marketing emails, promotional content, subscription-based emails, automated digests
  - "urgent_issue": Time-sensitive problems requiring immediate attention (outages, critical bugs, emergencies)
  - "spam": Junk mail, phishing attempts, scam emails, unsolicited commercial content
  - "general_inquiry": General questions, information requests, casual conversation
  - "follow_up": Continuation of an existing conversation, checking on previous request
  - "complaint": Negative feedback, dissatisfaction, issue reports
  - "action_required": Tasks, assignments, requests that need a specific action or response

PRIORITY LEVELS:
  - "high": Needs attention within hours (urgent issues, time-sensitive requests)
  - "medium": Needs attention within a day (meeting requests, general inquiries)
  - "low": Can wait or is informational only (newsletters, FYIs)

CONFIDENCE SCORING GUIDELINES:
  - 0.95-1.00: Obvious classification (clear spam, explicit meeting request with date/time)
  - 0.80-0.95: Strong indicators but some ambiguity
  - 0.60-0.80: Mixed signals, could be multiple categories
  - Below 0.60: Very uncertain, email is ambiguous

ENTITY EXTRACTION:
  - dates: Any dates, times, deadlines mentioned (e.g., "Friday", "3pm", "June 20th")
  - names: People's names mentioned in the email
  - action_items: Specific tasks or requests (e.g., "review document", "schedule meeting")

EXAMPLES:

Example 1:
  From: john@company.com
  Subject: Can we sync Thursday at 2pm?
  Body: Hey, I'd like to discuss the Q3 roadmap. Are you free Thursday at 2pm?
  Classification:
  {{"intent": "meeting_request", "priority": "medium", "confidence": 0.95, "entities": {{"dates": ["Thursday", "2pm"], "names": ["John"], "action_items": ["schedule meeting to discuss Q3 roadmap"]}}, "suggested_action": "draft_reply", "reasoning": "Explicit meeting request with specific date and time proposed"}}

Example 2:
  From: deals@megastore.com
  Subject: 🔥 MASSIVE SALE - 70% OFF!!!
  Body: Don't miss our biggest sale of the year! Shop now and save big!
  Classification:
  {{"intent": "newsletter", "priority": "low", "confidence": 0.97, "entities": {{"dates": [], "names": [], "action_items": []}}, "suggested_action": "archive", "reasoning": "Promotional marketing email with sales language and no personal content"}}

Example 3:
  From: client@bigcorp.com
  Subject: URGENT: Production API is returning 500 errors
  Body: Our production environment started throwing 500 errors 10 minutes ago. Multiple customers are affected. Need immediate help.
  Classification:
  {{"intent": "urgent_issue", "priority": "high", "confidence": 0.96, "entities": {{"dates": ["10 minutes ago"], "names": [], "action_items": ["investigate 500 errors", "fix production API"]}}, "suggested_action": "flag_and_draft", "reasoning": "Critical production issue affecting customers, requires immediate response"}}

NOW CLASSIFY THE EMAIL ABOVE.

Return ONLY valid JSON with this exact structure (no markdown, no code blocks, no extra text):
{{"intent": "category", "priority": "level", "confidence": 0.00, "entities": {{"dates": [], "names": [], "action_items": []}}, "suggested_action": "action", "reasoning": "explanation"}}"""

        return prompt

    def _parse_classification_response(self, raw_text: str) -> ClassificationResult:
        """
        Parse Gemini's response into a ClassificationResult.
        Handles common formatting issues.
        """
        # Clean up the response
        cleaned = raw_text.strip()

        # Remove markdown code blocks if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Parse JSON
        data = json.loads(cleaned)

        # Validate and extract fields with safe defaults
        valid_intents = [
            "meeting_request",
            "newsletter",
            "urgent_issue",
            "spam",
            "general_inquiry",
            "follow_up",
            "complaint",
            "action_required",
        ]
        valid_priorities = ["high", "medium", "low"]

        intent = data.get("intent", "general_inquiry")
        if intent not in valid_intents:
            logger.warning(
                f"Unknown intent '{intent}', defaulting to 'general_inquiry'"
            )
            intent = "general_inquiry"

        priority = data.get("priority", "medium")
        if priority not in valid_priorities:
            priority = "medium"

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp between 0 and 1

        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {"dates": [], "names": [], "action_items": []}

        # Ensure entity sub-fields exist
        entities.setdefault("dates", [])
        entities.setdefault("names", [])
        entities.setdefault("action_items", [])

        return ClassificationResult(
            intent=intent,
            priority=priority,
            confidence=confidence,
            entities=entities,
            suggested_action=data.get("suggested_action", "none"),
            reasoning=data.get("reasoning", "No reasoning provided"),
        )

    def _retry_classification(self, email_data: EmailData) -> ClassificationResult:
        """
        Retry classification with a simpler prompt if first attempt fails.
        """
        logger.info("Retrying classification with simplified prompt...")

        simple_prompt = f"""Classify this email. Return ONLY valid JSON.

From: {email_data.from_address}
Subject: {email_data.subject}
Body: {email_data.body[:500]}

JSON format:
{{"intent": "meeting_request|newsletter|urgent_issue|spam|general_inquiry|follow_up|complaint|action_required", "priority": "high|medium|low", "confidence": 0.0-1.0, "entities": {{"dates": [], "names": [], "action_items": []}}, "suggested_action": "reply|draft_reply|archive|flag|ignore", "reasoning": "brief explanation"}}"""

        try:
            self._rate_limit_wait()
            response = self.model.generate_content(simple_prompt)
            return self._parse_classification_response(response.text.strip())
        except Exception as e:
            logger.error(f"Retry classification also failed: {e}")
            return self._fallback_classification(str(e))

    def _fallback_classification(self, error_msg: str) -> ClassificationResult:
        """
        Return a safe fallback classification when AI fails.
        Low confidence ensures safety module will block auto-actions.
        """
        return ClassificationResult(
            intent="general_inquiry",
            priority="medium",
            confidence=0.0,  # Zero confidence -> safety will block everything
            entities={"dates": [], "names": [], "action_items": []},
            suggested_action="none",
            reasoning=f"Fallback classification due to error: {error_msg}",
        )

    # ──────────────────────────────────────────────
    # REPLY GENERATION
    # ──────────────────────────────────────────────

    def generate_reply(
        self,
        email_data: EmailData,
        classification: ClassificationResult,
        template: Optional[str] = None,
    ) -> Optional[str]:
        if template:
            try:
                self._rate_limit_wait()
                response = self.model.generate_content(template)
                reply_text = response.text.strip()
                reply_text = self._clean_reply(reply_text)
                return reply_text
            except Exception as e:
                logger.error(f"Reply generation from template failed: {e}")
                return None
        prompt = self._build_reply_prompt(email_data, classification)

        try:
            self._rate_limit_wait()
            response = self.model.generate_content(prompt)
            reply_text = response.text.strip()

            # Basic cleanup
            reply_text = self._clean_reply(reply_text)
            return reply_text

        except Exception as e:
            logger.error(f"Reply generation failed: {e}")
            return None

    def _build_reply_prompt(
        self,
        email_data: EmailData,
        classification: ClassificationResult,
    ) -> str:
        """Build the reply generation prompt."""

        # Customize tone based on intent
        tone_guidance = self._get_tone_guidance(
            classification.intent, classification.priority
        )

        prompt = f"""You are a professional email assistant. Generate a reply to the following email.

ORIGINAL EMAIL:
  From: {email_data.from_address}
  Subject: {email_data.subject}
  Body:
  {email_data.body[:2000]}

CONTEXT:
  This email was classified as: {classification.intent}
  Priority: {classification.priority}
  Key entities found: {json.dumps(classification.entities)}

TONE AND STYLE GUIDANCE:
{tone_guidance}

RULES:
  - Be professional but warm and human-sounding
  - Be concise (3-6 sentences unless more detail is needed)
  - Reference specific details from the original email
  - Do NOT make up facts, commitments, or specific times unless asked
  - Do NOT include a subject line — just the reply body
  - Do NOT include "Dear" or overly formal greetings — keep it natural
  - End with a simple sign-off like "Best regards" or "Thanks"
  - Do NOT use placeholder text like [Your Name] — just end with the sign-off

Generate the reply now:"""

        return prompt

    def _get_tone_guidance(self, intent: str, priority: str) -> str:
        """Get tone guidance based on email intent and priority."""

        guidance = {
            "meeting_request": (
                "  - Respond positively to the meeting request\n"
                "  - Acknowledge the proposed time if one was given\n"
                "  - If no time was proposed, suggest being open to scheduling\n"
                "  - Keep it brief and friendly"
            ),
            "urgent_issue": (
                "  - Acknowledge the urgency immediately\n"
                "  - Show that you take the issue seriously\n"
                "  - Indicate that you are looking into it / taking action\n"
                "  - Provide a timeline for follow-up if possible\n"
                "  - Be empathetic but action-oriented"
            ),
            "complaint": (
                "  - Be empathetic and understanding\n"
                "  - Acknowledge the issue without being defensive\n"
                "  - Express commitment to resolving the problem\n"
                "  - Ask for any additional details if needed\n"
                "  - Be apologetic where appropriate"
            ),
            "general_inquiry": (
                "  - Be helpful and informative\n"
                "  - Answer the question if you can\n"
                "  - If you need more information, ask specific questions\n"
                "  - Keep it conversational"
            ),
            "follow_up": (
                "  - Acknowledge the follow-up\n"
                "  - Reference the previous conversation context\n"
                "  - Provide an update or next steps\n"
                "  - Be brief"
            ),
            "action_required": (
                "  - Acknowledge the request\n"
                "  - Confirm you've received it\n"
                "  - Indicate when you'll complete the action or follow up\n"
                "  - Ask clarifying questions if the request is unclear"
            ),
        }

        return guidance.get(
            intent, "  - Be professional and helpful\n  - Keep it concise"
        )

    def _clean_reply(self, reply_text: str) -> str:
        """Clean up the generated reply text."""

        # Remove any markdown formatting
        reply_text = reply_text.strip()

        # Remove leading "Subject:" line if AI included one
        lines = reply_text.split("\n")
        if lines and lines[0].lower().startswith("subject:"):
            lines = lines[1:]
            reply_text = "\n".join(lines).strip()

        # Remove surrounding quotes if present
        if reply_text.startswith('"') and reply_text.endswith('"'):
            reply_text = reply_text[1:-1]

        return reply_text

    # ──────────────────────────────────────────────
    # CONNECTION TEST
    # ──────────────────────────────────────────────

    def test_connection(self) -> bool:
        """
        Test that Gemini API is accessible.
        Sends a simple prompt to verify the API key and model work.
        """
        try:
            self._rate_limit_wait()
            response = self.model.generate_content("Reply with exactly: OK")
            if response and response.text:
                logger.info("[OK] Gemini API connection successful")
                return True
            else:
                logger.error("❌ Gemini returned empty response")
                return False
        except Exception as e:
            logger.error(f"❌ Gemini API connection failed: {e}")
            return False
