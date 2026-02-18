# Design Decisions and Tradeoffs

## 1. IMAP/SMTP vs Gmail API
**Decision**: IMAP/SMTP with App Passwords (as required by spec)
**Tradeoff**: Less user-friendly setup, but demonstrates understanding of email protocols.
**Production alternative**: Gmail API with OAuth2 for seamless user experience.

## 2. Safe by Default
**Decision**: dry_run=true and auto_send=false as defaults
**Reasoning**: An AI agent sending emails autonomously is high-risk. Defaults should prevent accidental sends. Users must explicitly opt into live mode.

## 3. First-Match-Wins Rule Engine
**Decision**: Rules processed in order, first match wins
**Alternative considered**: Scoring-based system where multiple rules could contribute
**Reasoning**: First-match is simpler, predictable, and easier to debug. Users can control priority by rule ordering.

## 4. Fallback Classification on API Failure
**Decision**: Return classification with 0.0 confidence when Gemini fails
**Reasoning**: Zero confidence ensures the safety module blocks all auto-actions. The email is effectively "skipped" without crashing. Better to do nothing than do the wrong thing.

## 5. Rate Limiting Strategy
**Decision**: 15-second delay between Gemini API calls
**Reasoning**: Gemini free tier allows 5 RPM and 20 RPD. The delay prevents hitting RPM limits. For RPD, minimizing retries through better JSON parsing is critical.

## 6. Multi-Layer JSON Parsing
**Decision**: 6-step parsing pipeline (clean -> extract -> fix newlines -> parse -> fix braces -> regex)
**Reasoning**: Gemini frequently returns slightly malformed JSON. Rather than wasting API calls on retries, we aggressively fix common issues. This reduced API usage by approximately 40%.

## 7. Email Threading via Headers
**Decision**: Use In-Reply-To and References headers for threading
**Alternative**: Gmail API thread IDs
**Reasoning**: Standard email headers work with any provider. Gmail shows replies in the same thread when these headers are set correctly.

## 8. Separate Secrets from Configuration
**Decision**: Credentials in .env, behavior in config.yaml
**Reasoning**: .env is never committed to git (security). config.yaml can be shared and version-controlled. This is industry standard practice.

## What I Would Improve With More Time
- Implement Gemini JSON mode for guaranteed structured output
- Add webhook-based email notifications instead of IMAP polling
- Build a simple web dashboard for monitoring agent decisions
- Add email thread context to improve classification of replies
- Implement cost tracking per API call
- Add Docker support for easy deployment