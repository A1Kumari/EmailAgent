# Prompt Engineering Approach

## Classification Prompt Design

### Structure
The classification prompt follows a 7-part structure:

1. **Role**: "You are an expert email classification assistant"
2. **Task**: "Analyze the following email and classify it"
3. **Email Content**: From, To, Subject, Date, Body (truncated to 2000 chars)
4. **Categories**: 8 intent types with clear descriptions
5. **Confidence Guidelines**: Specific ranges with examples
6. **Few-Shot Examples**: 3 examples covering different categories
7. **Output Format**: Exact JSON schema specification

### Why This Structure Works
- **Role setting** prevents the model from being too generic
- **Category descriptions** reduce ambiguity between similar intents
- **Confidence guidelines** prevent the model from always returning 0.95
- **Few-shot examples** ground the model's understanding of expected output
- **Strict JSON format** enables reliable parsing

### Challenges Encountered
1. **JSON truncation**: Gemini sometimes cuts off JSON mid-string for long reasoning fields. Fixed with multi-layer JSON parsing (regex extraction as fallback).
2. **Confidence calibration**: Without guidelines, model returns 0.95+ for everything. Added specific score ranges with descriptions.
3. **Entity extraction**: Model occasionally misses entities. Added explicit instructions and examples.

## Reply Generation Prompt Design

### Intent-Specific Tone Guidance
Each email intent gets customized tone instructions:
- **Meeting requests**: Positive, mention proposed time, brief
- **Urgent issues**: Acknowledge urgency, promise action, empathetic
- **Complaints**: Empathetic, non-defensive, solution-oriented
- **General inquiries**: Helpful, informative, conversational

### Safety Rules in Prompts
The reply prompt includes explicit safety rules:
- "Do NOT make up facts or commitments"
- "Do NOT include placeholder text like [Your Name]"
- "Be concise (3-6 sentences)"

This prevents the AI from making promises or generating unrealistic responses.