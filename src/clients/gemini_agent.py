# src/gemini_agent.py

"""
Gemini AI Agent (Enhanced)
Handles all interactions with Google Gemini 2.5 Flash.

Features:
  - Email classification (intent, priority, confidence, entities)
  - Reply generation (contextual, professional responses)
  - R1: Structured output via Gemini JSON mode
  - R2: Email thread context awareness
  - R3: Cost tracking for API usage
  - R4: Function calling for structured action suggestions
  - R6: Full backward compatibility with legacy parsing
  - R7: Feature flags for toggling enhancements
  - R8: Graceful error handling with fallbacks
  - R9: Comprehensive logging and observability
"""

import json
import logging
import time
from typing import Optional

import google.generativeai as genai

from src.core.models import EmailData, ClassificationResult
from src.utils.config_manager import GeminiConfig

logger = logging.getLogger(__name__)


class GeminiAgent:
    """
    AI agent powered by Gemini 2.5 Flash.

    Responsibilities:
      - Classify emails (intent, priority, confidence, entities)
      - Generate contextual reply drafts
      - Provide structured action suggestions via function calling
      - Track API costs

    Usage:
        agent = GeminiAgent(config.gemini, feature_flags=flags, cost_tracker=tracker)
        classification = agent.classify_email(email_data)
        reply = agent.generate_reply(email_data, classification)
    """

    # ──────────────────────────────────────────────
    # CLASS-LEVEL CONSTANTS
    # ──────────────────────────────────────────────

    # R1: JSON schema for classification (used by JSON mode)
    CLASSIFICATION_SCHEMA = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "meeting_request",
                    "newsletter",
                    "urgent_issue",
                    "spam",
                    "general_inquiry",
                    "follow_up",
                    "complaint",
                    "action_required",
                ],
            },
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score from 0.0 to 1.0",
            },
            "entities": {
                "type": "object",
                "properties": {
                    "dates": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "action_items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["dates", "names", "action_items"],
            },
            "suggested_action": {
                "type": "string",
                "enum": [
                    "reply",
                    "draft_reply",
                    "archive",
                    "flag",
                    "ignore",
                    "flag_and_draft",
                ],
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation for the classification",
            },
        },
        "required": [
            "intent",
            "priority",
            "confidence",
            "entities",
            "suggested_action",
            "reasoning",
        ],
    }

    # R3: Gemini 2.5 Flash pricing per 1M tokens
    PRICING = {
        "input_per_1m": 0.075,
        "output_per_1m": 0.30,
    }

    # ──────────────────────────────────────────────
    # INITIALIZATION
    # ──────────────────────────────────────────────

    def __init__(
        self,
        config: GeminiConfig,
        feature_flags: Optional[dict] = None,
        cost_tracker=None,
    ):
        self.config = config

        # R7: Feature flags with safe defaults
        self.features = feature_flags or {
            "use_json_mode": True,
            "use_function_calling": True,
            "enable_cost_tracking": True,
            "thread_context_depth": 5,
        }

        # R3: Cost tracker (injected dependency)
        self.cost_tracker = cost_tracker

        # Rate limiting
        self._last_api_call = 0
        self._min_delay = 15  # 15 seconds between calls (safe for 5 RPM)
        self._call_count = 0

        # R6: Always setup the base/legacy model first
        self._setup_client()

        # R1: Setup JSON mode model if enabled
        self.json_mode_model = None
        if self.features.get("use_json_mode", True):
            self._setup_json_mode_model()

        # R4: Setup function calling model if enabled
        self.function_calling_model = None
        if self.features.get("use_function_calling", True):
            self._setup_function_calling()

        # R9: Log feature status at startup
        logger.info(f"GeminiAgent initialized | model={self.config.model}")
        logger.info(f"  JSON mode:        {'ON' if self.json_mode_model else 'OFF'}")
        logger.info(
            f"  Function calling: {'ON' if self.function_calling_model else 'OFF'}"
        )
        logger.info(f"  Cost tracking:    {'ON' if self.cost_tracker else 'OFF'}")
        logger.info(
            f"  Thread depth:     {self.features.get('thread_context_depth', 5)}"
        )

    def _setup_client(self):
        """
        Initialize the base Gemini client.
        R6: This is the legacy/fallback model — always available.
        """
        genai.configure(api_key=self.config.api_key)
        self.model = genai.GenerativeModel(
            model_name=self.config.model,
            generation_config=genai.GenerationConfig(
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
            ),
        )
        logger.debug(f"Base Gemini model initialized: {self.config.model}")

    def _setup_json_mode_model(self):
        """
        R1: Create a model configured for Gemini's native JSON mode.
        This guarantees valid JSON output matching our classification schema.
        Eliminates the need for the 6-step parsing pipeline.
        """
        try:
            self.json_mode_model = genai.GenerativeModel(
                model_name=self.config.model,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=self.CLASSIFICATION_SCHEMA,
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                ),
            )
            logger.info("[R1] JSON mode model initialized with classification schema")
            logger.debug(
                f"[R1] Schema fields: {list(self.CLASSIFICATION_SCHEMA['properties'].keys())}"
            )
        except Exception as e:
            logger.error(f"[R1] Failed to setup JSON mode model: {e}")
            logger.warning("[R1] Will fall back to legacy text parsing")
            self.json_mode_model = None

    def _setup_function_calling(self):
        """
        R4: Configure Gemini with function declarations for structured actions.
        The model can "call" these functions to suggest email actions with
        typed parameters.
        """
        suggest_email_action = genai.protos.FunctionDeclaration(
            name="suggest_email_action",
            description=(
                "Suggest an action to take on an email based on its content "
                "and classification. Call this function to recommend what the "
                "email agent should do."
            ),
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "action_type": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        enum=[
                            "reply",
                            "draft_reply",
                            "archive",
                            "flag",
                            "ignore",
                            "flag_and_draft",
                        ],
                        description="The recommended action to take",
                    ),
                    "confidence": genai.protos.Schema(
                        type=genai.protos.Type.NUMBER,
                        description="How confident the suggestion is (0.0 to 1.0)",
                    ),
                    "reasoning": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        description="Why this action is recommended",
                    ),
                    "reply_template_hint": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        description=(
                            "If action involves a reply, describe the tone "
                            "and key points to include"
                        ),
                    ),
                },
                required=["action_type", "confidence", "reasoning"],
            ),
        )

        tool = genai.protos.Tool(function_declarations=[suggest_email_action])

        try:
            self.function_calling_model = genai.GenerativeModel(
                model_name=self.config.model,
                tools=[tool],
                generation_config=genai.GenerationConfig(
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                ),
            )
            logger.info(
                "[R4] Function calling model initialized with suggest_email_action tool"
            )
        except Exception as e:
            logger.error(f"[R4] Failed to setup function calling: {e}")
            self.function_calling_model = None

    # ──────────────────────────────────────────────
    # RATE LIMITING
    # ──────────────────────────────────────────────

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

    # ──────────────────────────────────────────────
    # COST TRACKING (R3)
    # ──────────────────────────────────────────────

    def _extract_and_track_cost(self, response, operation: str = "unknown"):
        """
        R3: Extract token usage from Gemini response and track cost.

        Gemini 2.5 Flash pricing:
          - Input:  \$0.075 per 1M tokens
          - Output: \$0.30  per 1M tokens
        """
        if not self.features.get("enable_cost_tracking", False):
            return
        if not self.cost_tracker:
            return

        try:
            usage_metadata = getattr(response, "usage_metadata", None)

            if usage_metadata is None:
                logger.debug("[R3] No usage metadata in response")
                return

            input_tokens = getattr(usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(usage_metadata, "candidates_token_count", 0)
            total_tokens = getattr(usage_metadata, "total_token_count", 0)

            # Calculate costs
            input_cost = (input_tokens / 1_000_000) * self.PRICING["input_per_1m"]
            output_cost = (output_tokens / 1_000_000) * self.PRICING["output_per_1m"]
            total_cost = input_cost + output_cost

            # Record in cost tracker
            self.cost_tracker.record(
                operation=operation,
                model=self.config.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                total_cost=total_cost,
            )

            # R9: Log cost info after each call
            logger.info(
                f"[R3] API Cost | op={operation} "
                f"in_tokens={input_tokens} out_tokens={output_tokens} "
                f"cost=${total_cost:.6f}"
            )

        except Exception as e:
            # R8: Cost tracking failure should never block email processing
            logger.warning(
                f"[R8] Cost tracking failed: {e}. Continuing without tracking."
            )

    # ──────────────────────────────────────────────
    # THREAD CONTEXT (R2)
    # ──────────────────────────────────────────────

    def _build_thread_context(self, email_data: EmailData) -> str:
        """
        R2: Build formatted thread context from previous messages.

        Uses In-Reply-To and References headers to identify thread.
        Limits to configured depth (default: 5 messages).

        Args:
            email_data: The current email (may contain thread_messages)

        Returns:
            Formatted string of previous messages, or "" if none available.
        """
        max_depth = self.features.get("thread_context_depth", 5)

        if not hasattr(email_data, "thread_messages") or not email_data.thread_messages:
            logger.debug("[R2] No thread messages available for this email")
            return ""

        try:
            # Take only the most recent N messages
            all_thread_msgs = email_data.thread_messages
            recent_messages = all_thread_msgs[-max_depth:]

            logger.info(
                f"[R2] Building thread context: "
                f"{len(recent_messages)} of {len(all_thread_msgs)} "
                f"messages (depth limit: {max_depth})"
            )

            context_parts = []
            total = len(recent_messages)

            for i, msg in enumerate(recent_messages):
                sender = msg.get("from", "Unknown")
                date = msg.get("date", "Unknown date")
                body = msg.get("body", "")
                subject = msg.get("subject", "")

                # Truncate: recent messages get more body text
                is_recent = i >= (total - 2)
                max_body_len = 500 if is_recent else 200
                body_preview = body[:max_body_len]
                if len(body) > max_body_len:
                    body_preview += "..."

                marker = " [LATEST]" if i == total - 1 else ""

                context_parts.append(
                    f"  [{i + 1}/{total}]{marker}\n"
                    f"    From: {sender}\n"
                    f"    Date: {date}\n"
                    f"    Subject: {subject}\n"
                    f"    Body: {body_preview}\n"
                )

            context = "\n".join(context_parts)

            # R9: Log context stats
            logger.debug(
                f"[R2] Thread context built: {len(context)} chars, {total} messages"
            )
            return context

        except Exception as e:
            # R8: Thread fetch failure should not block classification
            logger.warning(
                f"[R8] Thread context building failed: {e}. "
                f"Proceeding without thread context."
            )
            return ""

    # ──────────────────────────────────────────────
    # EMAIL CLASSIFICATION
    # ──────────────────────────────────────────────

    def classify_email(self, email_data: EmailData) -> ClassificationResult:
        """
        Classify an email using Gemini.

        Flow (based on feature flags):
          1. Build thread context (R2)
          2. If JSON mode ON  → use structured output (R1)
             If JSON mode OFF → use legacy text parsing (R6)
          3. Extract cost data from response (R3)
          4. If function calling ON → get action suggestion (R4)

        Args:
            email_data: The email to classify

        Returns:
            ClassificationResult with intent, priority, confidence, entities
        """
        # R2: Build thread context
        thread_context = self._build_thread_context(email_data)

        # R1/R6: Choose classification path based on feature flag
        if self.features.get("use_json_mode", True) and self.json_mode_model:
            logger.info("[R1] Using JSON mode for classification")
            classification, response = self._classify_with_json_mode(
                email_data, thread_context
            )
        else:
            logger.info("[R6] Using legacy text parsing for classification")
            classification, response = self._classify_with_legacy(
                email_data, thread_context
            )

        # R3: Track cost
        if response is not None:
            self._extract_and_track_cost(response, operation="classify")

        # R4: Get function calling suggestion if enabled
        if (
            self.features.get("use_function_calling", True)
            and self.function_calling_model
            and classification.confidence > 0
        ):
            action_suggestion = self._get_function_call_suggestion(
                email_data, thread_context
            )
            if action_suggestion:
                # Store the structured action suggestion on the classification
                # This is additive — doesn't replace suggested_action from classification
                classification.function_call_suggestion = action_suggestion
                logger.info(
                    f"[R4] Function call suggested: "
                    f"{action_suggestion.get('action_type')} "
                    f"(conf: {action_suggestion.get('confidence', 'N/A')})"
                )

        # R9: Log the final classification result
        logger.info(
            f"Classification complete | "
            f"intent={classification.intent} "
            f"priority={classification.priority} "
            f"confidence={classification.confidence:.2f} "
            f"action={classification.suggested_action}"
        )

        return classification

    # ──────────────────────────────────────────────
    # R1: JSON MODE CLASSIFICATION
    # ──────────────────────────────────────────────

    def _classify_with_json_mode(
        self, email_data: EmailData, thread_context: str
    ) -> tuple:
        """
        R1: Classify using Gemini JSON mode — guaranteed valid JSON.
        No manual parsing pipeline needed.

        Returns:
            Tuple of (ClassificationResult, raw_response)
        """
        prompt = self._build_classification_prompt(
            email_data, thread_context, simplified=True
        )

        try:
            self._rate_limit_wait()
            response = self.json_mode_model.generate_content(prompt)

            # JSON mode guarantees valid JSON — direct parse, no cleanup needed
            data = json.loads(response.text)

            logger.debug(
                f"[R1] JSON mode raw response: {json.dumps(data, indent=2)[:500]}"
            )
            logger.info(
                f"[R1] JSON mode returned valid structured output "
                f"(schema: {len(self.CLASSIFICATION_SCHEMA['properties'])} fields)"
            )

            # Build ClassificationResult directly from validated JSON
            classification = ClassificationResult(
                intent=data["intent"],
                priority=data["priority"],
                confidence=max(0.0, min(1.0, float(data["confidence"]))),
                entities=data.get(
                    "entities",
                    {"dates": [], "names": [], "action_items": []},
                ),
                suggested_action=data.get("suggested_action", "none"),
                reasoning=data.get("reasoning", "No reasoning provided"),
            )
            return classification, response

        except json.JSONDecodeError as e:
            # R8: JSON mode should not produce invalid JSON, but handle it
            logger.error(
                f"[R8] JSON mode returned invalid JSON (unexpected): {e}. "
                f"Falling back to legacy parsing."
            )
            return self._classify_with_legacy(email_data, thread_context)

        except Exception as e:
            # R8: Any other failure falls back to legacy
            logger.warning(
                f"[R8] JSON mode classification failed: {e}. "
                f"Falling back to legacy parsing."
            )
            return self._classify_with_legacy(email_data, thread_context)

    # ──────────────────────────────────────────────
    # R6: LEGACY CLASSIFICATION (backward compatible)
    # ──────────────────────────────────────────────

    def _classify_with_legacy(
        self, email_data: EmailData, thread_context: str
    ) -> tuple:
        """
        R6: Legacy classification path — preserves full backward compatibility.
        Uses text-based prompt + manual JSON parsing (the original 6-step pipeline).

        Returns:
            Tuple of (ClassificationResult, raw_response or None)
        """
        prompt = self._build_classification_prompt(
            email_data, thread_context, simplified=False
        )

        try:
            self._rate_limit_wait()
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip()
            logger.debug(f"[R6] Legacy raw response: {raw_text[:200]}...")
            classification = self._parse_classification_response(raw_text)
            return classification, response

        except json.JSONDecodeError as e:
            logger.warning(f"[R6] Failed to parse Gemini JSON response: {e}")
            classification = self._retry_classification(email_data)
            return classification, None

        except Exception as e:
            logger.error(f"[R6] Legacy classification failed: {e}")
            classification = self._fallback_classification(str(e))
            return classification, None

    # ──────────────────────────────────────────────
    # R4: FUNCTION CALLING
    # ──────────────────────────────────────────────

    def _get_function_call_suggestion(
        self, email_data: EmailData, thread_context: str
    ) -> Optional[dict]:
        """
        R4: Use Gemini function calling to get a structured action suggestion.

        Returns:
            Dict with action_type, confidence, reasoning, reply_template_hint
            or None if function calling fails or returns no call.
        """
        prompt = f"""Analyze this email and suggest the best action to take.

EMAIL:
  From: {email_data.from_address}
  Subject: {email_data.subject}
  Body: {email_data.body[:1500]}
"""
        if thread_context:
            prompt += f"""
THREAD CONTEXT (previous messages):
{thread_context}
"""

        prompt += """
Based on the email content and any thread context, call the suggest_email_action 
function with your recommended action."""

        try:
            self._rate_limit_wait()
            response = self.function_calling_model.generate_content(prompt)

            # R3: Track cost for function calling
            self._extract_and_track_cost(response, operation="function_call")

            # Extract function call from response
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        if fc.name == "suggest_email_action":
                            args = dict(fc.args)

                            suggestion = {
                                "action_type": args.get("action_type", "ignore"),
                                "confidence": float(args.get("confidence", 0.5)),
                                "reasoning": args.get("reasoning", ""),
                                "reply_template_hint": args.get(
                                    "reply_template_hint", ""
                                ),
                            }

                            logger.info(
                                f"[R4] Function call result: "
                                f"action={suggestion['action_type']} "
                                f"conf={suggestion['confidence']:.2f}"
                            )
                            logger.debug(
                                f"[R4] Full suggestion: {json.dumps(suggestion, indent=2)}"
                            )
                            return suggestion

            logger.debug("[R4] No function call found in response")
            return None

        except Exception as e:
            # R8: Function calling failure is non-fatal
            logger.warning(
                f"[R8] Function call suggestion failed: {e}. "
                f"Continuing with classification-only mode."
            )
            return None

    # ──────────────────────────────────────────────
    # PROMPT BUILDING
    # ──────────────────────────────────────────────

    def _build_classification_prompt(
        self,
        email_data: EmailData,
        thread_context: str = "",
        simplified: bool = False,
    ) -> str:
        """
        Build the classification prompt.

        Args:
            email_data: The email to classify
            thread_context: R2 — formatted thread history string
            simplified: R1 — if True, use shorter prompt (JSON mode
                        handles structure enforcement via schema)
        """

        # ── R1: Simplified prompt for JSON mode ──────────
        # When JSON mode is active, the schema enforces the output structure,
        # so we don't need the verbose format instructions and examples.
        if simplified:
            prompt = f"""You are an expert email classification assistant. Analyze this email and classify it accurately.

EMAIL TO CLASSIFY:
  From: {email_data.from_address}
  To: {email_data.to_address}
  Subject: {email_data.subject}
  Date: {email_data.date}
  Body:
{email_data.body[:2000]}
"""
            # R2: Add thread context if available
            if thread_context:
                prompt += f"""
PREVIOUS MESSAGES IN THIS THREAD:
{thread_context}
Use the thread context to better understand the email's intent and whether 
this is a follow-up, escalation, or new topic.
"""

            prompt += """
CLASSIFICATION GUIDELINES:
- intent: The primary purpose (meeting_request, newsletter, urgent_issue, spam, general_inquiry, follow_up, complaint, action_required)
- priority: "high" = within hours, "medium" = within a day, "low" = informational
- confidence: 0.95+ obvious, 0.80-0.95 strong signals, 0.60-0.80 mixed, below 0.60 uncertain
- entities: Extract any dates, people's names, and action items mentioned
- suggested_action: What should be done (reply, draft_reply, archive, flag, ignore, flag_and_draft)
- reasoning: Brief explanation of your classification decision

Classify this email now."""

            return prompt

        # ── R6: Full legacy prompt (backward compatible) ─
        # Kept exactly as original for when JSON mode is disabled.

        # R2: Include thread context in legacy prompt too
        thread_section = ""
        if thread_context:
            thread_section = f"\nPREVIOUS MESSAGES IN THREAD:\n{thread_context}\n"
        elif email_data.thread_messages:
            # Fallback to original thread handling if _build_thread_context
            # was not called or returned empty but raw data exists
            thread_section = "\nPREVIOUS MESSAGES IN THREAD:\n"
            for msg in email_data.thread_messages[-3:]:
                thread_section += f"  From: {msg.get('from', 'unknown')}\n"
                thread_section += f"  Body: {msg.get('body', '')[:200]}\n\n"

        prompt = f"""You are an expert email classification assistant. Your job is to analyze emails and return a structured classification.

TASK: Analyze the following email and classify it accurately.

EMAIL TO CLASSIFY:
  From: {email_data.from_address}
  To: {email_data.to_address}
  Subject: {email_data.subject}
  Date: {email_data.date}
  Body:
  {email_data.body[:2000]}
{thread_section}

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

    # ──────────────────────────────────────────────
    # LEGACY PARSING (R6: kept for backward compat)
    # ──────────────────────────────────────────────

    def _parse_classification_response(self, raw_text: str) -> ClassificationResult:
        """
        R6: Parse Gemini's text response into a ClassificationResult.
        Handles common formatting issues (markdown blocks, etc.).

        Only used when JSON mode is OFF (legacy path).
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
        R6: Retry classification with a simpler prompt if first attempt fails.
        Only used in legacy parsing path.
        """
        logger.info("[R6] Retrying classification with simplified prompt...")

        simple_prompt = f"""Classify this email. Return ONLY valid JSON.

From: {email_data.from_address}
Subject: {email_data.subject}
Body: {email_data.body[:500]}

JSON format:
{{"intent": "meeting_request|newsletter|urgent_issue|spam|general_inquiry|follow_up|complaint|action_required", "priority": "high|medium|low", "confidence": 0.0-1.0, "entities": {{"dates": [], "names": [], "action_items": []}}, "suggested_action": "reply|draft_reply|archive|flag|ignore", "reasoning": "brief explanation"}}"""

        try:
            self._rate_limit_wait()
            response = self.model.generate_content(simple_prompt)

            # R3: Track cost for retry
            self._extract_and_track_cost(response, operation="classify_retry")

            return self._parse_classification_response(response.text.strip())
        except Exception as e:
            logger.error(f"[R6] Retry classification also failed: {e}")
            return self._fallback_classification(str(e))

    def _fallback_classification(self, error_msg: str) -> ClassificationResult:
        """
        Return a safe fallback classification when AI fails.
        Low confidence ensures safety module will block auto-actions.
        Used by both JSON mode and legacy paths.
        """
        logger.warning(
            f"Using fallback classification (zero confidence) due to: {error_msg}"
        )
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
        """
        Generate a reply to an email.

        Args:
            email_data: The email to reply to
            classification: Classification result for context
            template: Optional template/prompt override

        Returns:
            Reply text string or None if generation fails
        """
        # Template-based generation
        if template:
            try:
                self._rate_limit_wait()
                response = self.model.generate_content(template)

                # R3: Track cost
                self._extract_and_track_cost(response, operation="reply_template")

                reply_text = response.text.strip()
                reply_text = self._clean_reply(reply_text)

                logger.info(
                    f"[Reply] Generated {len(reply_text)} char reply from template"
                )
                return reply_text
            except Exception as e:
                logger.error(f"Reply generation from template failed: {e}")
                return None

        # R2: Build thread context for reply generation
        thread_context = self._build_thread_context(email_data)

        # Build prompt with thread context
        prompt = self._build_reply_prompt(email_data, classification, thread_context)

        try:
            self._rate_limit_wait()
            response = self.model.generate_content(prompt)

            # R3: Track cost
            self._extract_and_track_cost(response, operation="reply_generation")

            reply_text = response.text.strip()
            reply_text = self._clean_reply(reply_text)

            # R9: Log reply generation
            logger.info(
                f"[Reply] Generated {len(reply_text)} char reply "
                f"for {classification.intent} email "
                f"(thread_context: {'yes' if thread_context else 'no'})"
            )

            return reply_text

        except Exception as e:
            logger.error(f"Reply generation failed: {e}")
            return None

    def _build_reply_prompt(
        self,
        email_data: EmailData,
        classification: ClassificationResult,
        thread_context: str = "",
    ) -> str:
        """
        Build the reply generation prompt.

        Args:
            email_data: The email to reply to
            classification: Classification for context
            thread_context: R2 — formatted thread history
        """
        tone_guidance = self._get_tone_guidance(
            classification.intent, classification.priority
        )

        # R2: Build thread context section
        thread_section = ""
        if thread_context:
            thread_section = f"""
CONVERSATION HISTORY (previous messages in this thread):
{thread_context}

IMPORTANT — Use the thread context to:
  - Reference previous points discussed
  - Maintain consistency with the conversation tone
  - Avoid repeating information already shared
  - Build on decisions already made
"""

        # R4: Include function call hint if available
        action_hint_section = ""
        if (
            hasattr(classification, "function_call_suggestion")
            and classification.function_call_suggestion
        ):
            hint = classification.function_call_suggestion.get(
                "reply_template_hint", ""
            )
            if hint:
                action_hint_section = f"""
AI ACTION SUGGESTION:
  The AI recommends: {classification.function_call_suggestion.get("action_type", "N/A")}
  Tone/content hint: {hint}
  Consider this suggestion when crafting the reply.
"""

        prompt = f"""You are a professional email assistant. Generate a reply to the following email.

ORIGINAL EMAIL:
  From: {email_data.from_address}
  Subject: {email_data.subject}
  Body:
  {email_data.body[:2000]}
{thread_section}{action_hint_section}
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

            # R3: Track even test calls
            self._extract_and_track_cost(response, operation="connection_test")

            if response and response.text:
                logger.info("[OK] Gemini API connection successful")

                # R9: Log model capabilities
                if self.json_mode_model:
                    logger.info("[OK] JSON mode model ready")
                if self.function_calling_model:
                    logger.info("[OK] Function calling model ready")

                return True
            else:
                logger.error("❌ Gemini returned empty response")
                return False
        except Exception as e:
            logger.error(f"❌ Gemini API connection failed: {e}")
            return False

    # ──────────────────────────────────────────────
    # UTILITY / STATUS
    # ──────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        R9: Get current agent status for observability.

        Returns:
            Dict with model info, feature status, call count, and cost summary.
        """
        status = {
            "model": self.config.model,
            "api_calls": self._call_count,
            "features": {
                "json_mode": self.json_mode_model is not None,
                "function_calling": self.function_calling_model is not None,
                "cost_tracking": self.cost_tracker is not None,
                "thread_context_depth": self.features.get("thread_context_depth", 5),
            },
        }

        # Include cost summary if available
        if self.cost_tracker and hasattr(self.cost_tracker, "get_summary"):
            status["cost_summary"] = self.cost_tracker.get_summary()

        return status
