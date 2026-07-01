# Provenance Guard

Provenance Guard is a Flask API for text-authorship attribution. A user submits text, the system runs two detection signals, combines them into an AI-likelihood score, returns a transparency label, records the decision in an audit log, and gives creators a way to appeal.

The project is not designed to prove authorship. It is designed to make automated attribution decisions visible, explainable, appealable, and auditable.

## Project Status

| Milestone | Status | Evidence |
|---|---|---|
| M3 | Complete | `POST /submit`, first Groq LLM signal, `GET /log`, structured audit entries |
| M4 | Complete | second stylometric signal, combined scoring, calibration examples |
| M5 | Complete | final labels, `/appeal`, rate limiting, complete audit log |
| M6 | In progress | README complete; walkthrough video link should be added after recording |

## Problem

AI-text detection is risky because polished human writing can look machine-generated, and edited AI output can look human. A detector that simply says “AI” or “human” with no explanation creates a false sense of certainty.

Provenance Guard addresses this by combining multiple imperfect signals, returning uncertainty when evidence is mixed, and allowing creators to appeal a classification. The goal is not an omniscient detector. The goal is a cautious transparency layer.

## Tech Stack

| Component | Tool |
|---|---|
| Backend API | Flask |
| LLM signal | Groq `llama-3.3-70b-versatile` |
| Structural signal | Pure-Python stylometric heuristics |
| Rate limiting | Flask-Limiter |
| Audit log | JSONL file |
| Environment | Python, `.env` for API key |

## Project Structure

```text
Provenance_Guard/
├── app.py              # Flask routes, signals, scoring, labels, audit logging
├── planning.md         # architecture, signal plan, uncertainty plan, AI tool plan
├── README.md           # final project documentation
├── requirements.txt    # project dependencies
├── .gitignore          # excludes .env, .venv, cache files, audit log
└── audit_log.jsonl     # runtime audit log, generated locally and gitignored
```

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```text
GROQ_API_KEY=your_groq_api_key_here
```

Run the app:

```bash
python app.py
```

The server runs at:

```text
http://localhost:5000
```

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | health check |
| `POST` | `/submit` | classify submitted text |
| `POST` | `/appeal` | appeal a classification |
| `GET` | `/log` | return recent audit-log entries |

## Architecture

### Submission Flow

```text
Client
  |
  | POST /submit {text, creator_id}
  v
Input validation
  |
  v
Signal 1: Groq LLM classifier
  | returns llm_score + llm_reason
  v
Signal 2: Stylometric heuristic checker
  | returns stylometry_score + metrics
  v
Score combiner
  | returns ai_likelihood + confidence
  v
Attribution mapper
  | likely_ai / likely_human / uncertain
  v
Transparency label generator
  |
  v
Structured JSONL audit log
  |
  v
JSON response
```

### Appeal Flow

```text
Client
  |
  | POST /appeal {content_id, creator_reasoning}
  v
Find original classification
  |
  v
Update status to under_review
  |
  v
Write appeal_submitted event
  |
  v
JSON confirmation
```

## Submission Workflow

1. A client sends a `POST /submit` request with `text` and `creator_id`.
2. The API validates the request body.
3. The text is evaluated by two detection signals:
   - Groq LLM classifier
   - stylometric heuristic checker
4. The two scores are combined into `ai_likelihood`.
5. The score maps to one of three attribution categories:
   - `likely_ai`
   - `likely_human`
   - `uncertain`
6. The system generates a plain-language transparency label.
7. The full decision is written to `audit_log.jsonl`.
8. The API returns the classification as JSON.

## Appeal Workflow

1. A creator sends a `POST /appeal` request with `content_id` and `creator_reasoning`.
2. The system looks up the original classification.
3. If the content exists, its status changes to `under_review`.
4. The appeal is written to the audit log as a separate event.
5. The API returns an appeal confirmation.

Automated reclassification is intentionally out of scope. An appeal introduces human review; it does not ask the detector to judge itself again.

## `POST /submit`

Required JSON body:

```json
{
  "text": "Text to evaluate",
  "creator_id": "creator identifier"
}
```

Example request:

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that stakeholders across various sectors must collaborate to ensure responsible deployment.", "creator_id": "test-ai"}' | PYTHON_COLORS=0 python -m json.tool
```

Example response fields:

```json
{
  "content_id": "1e1ac5a9-8d91-47c4-9ef1-183502c70069",
  "creator_id": "test-ai",
  "attribution": "likely_ai",
  "ai_likelihood": 0.7479,
  "confidence": 0.4958,
  "combined_score": 0.7479,
  "label": "This work shows strong signs of AI-generated text based on an automated multi-signal review. This label is not a final judgment of authorship and may be appealed by the creator.",
  "signals": {
    "llm": {
      "score": 0.8,
      "reason": "The text features generic phrasing, polished structure, and formulaic transitions, which are characteristic of AI-generated content."
    },
    "stylometry": {
      "score": 0.6511
    }
  },
  "status": "classified"
}
```

## Detection Signals

The system uses two signals because no single detector is reliable enough on its own. The LLM signal evaluates broad style and semantic patterns. The stylometric signal measures inspectable surface features. Their disagreement is useful because it exposes uncertainty.

| Signal | What it measures | Why it helps | What it misses |
|---|---|---|---|
| Groq LLM classifier | Generic phrasing, formulaic structure, polished but impersonal tone, lack of specific lived detail | Captures whole-passage style and meaning better than hand-written rules | Can falsely flag polished, formal, academic, professional, or non-native-English human writing |
| Stylometric heuristics | Word count, sentence count, average sentence length, sentence length variance, type-token ratio, punctuation density, contractions, first-person language, slang, all-caps words | Transparent, deterministic, cheap, and inspectable | Cannot understand meaning; weak on short text; formal human writing can look structurally AI-like |

### Signal 1: Groq LLM Classifier

The Groq signal asks `llama-3.3-70b-versatile` to classify whether the submitted text reads as AI-like or human-like. It returns a score from `0.0` to `1.0`.

```text
0.0 = strongly human-like
1.0 = strongly AI-like
```

This signal is useful because it can notice broad patterns such as generic phrasing, overly smooth transitions, hedged structure, and a lack of concrete personal detail. Its weakness is that those same traits can appear in formal human writing.

### Signal 2: Stylometric Heuristic Checker

The stylometric signal computes structural features directly from the text. It checks:

- word count
- sentence count
- average sentence length
- sentence length variance
- type-token ratio
- punctuation density
- contraction count
- first-person count
- slang count
- all-caps count

These metrics are combined into a stylometry score from `0.0` to `1.0`, where higher values indicate more AI-like structure.

This signal is useful because it is explainable. The audit log shows the exact metrics. Its weakness is that surface style is not authorship. A careful human writer may produce uniform prose, while edited AI text may include casual human-like irregularity.

## Confidence Scoring

The system reports two related but different values.

`ai_likelihood` is the direction of the evidence. A value near `1.0` means the signals lean AI-like. A value near `0.0` means the signals lean human-like. A value near `0.5` means the evidence is mixed or borderline.

`confidence` is how far the result is from the uncertain middle. It is computed as:

```python
confidence = abs(ai_likelihood - 0.5) * 2
```

This means a low AI-likelihood can still have high confidence if the system strongly believes the text is human-like. For example, the casual human example has `ai_likelihood = 0.1877` and `confidence = 0.6246`, because it is far from the uncertain middle.

The combined AI-likelihood score is computed with a weighted average:

```python
ai_likelihood = (0.65 * llm_score) + (0.35 * stylometry_score)
```

The LLM signal receives more weight because it judges the whole passage, while the stylometric signal is narrower but more transparent.

### Classification Thresholds

| AI likelihood | Attribution |
|---|---|
| `>= 0.70` | `likely_ai` |
| `<= 0.34` | `likely_human` |
| `0.35–0.69` | `uncertain` |

The uncertainty band is deliberately wide. A borderline case should not become an accusation.

## Calibration Results

These are real results from local M5 testing.

| Test case | LLM score | Stylometry score | AI likelihood | Confidence | Attribution |
|---|---:|---:|---:|---:|---|
| AI-like formal paragraph | 0.8000 | 0.6511 | 0.7479 | 0.4958 | `likely_ai` |
| Casual human ramen review | 0.1200 | 0.3133 | 0.1877 | 0.6246 | `likely_human` |
| Borderline remote-work paragraph | 0.4000 | 0.6282 | 0.4799 | 0.0402 | `uncertain` |

The human-like and borderline examples show the confidence logic clearly. The human-like example is far from the uncertain middle, so it receives a higher confidence score. The borderline example is very close to `0.5`, so confidence drops to `0.0402` and the system returns `uncertain`.

## Example Scoring Results

### AI-like example

```json
{
  "attribution": "likely_ai",
  "confidence": 0.4958,
  "ai_likelihood": 0.7479,
  "combined_score": 0.7479,
  "llm_score": 0.8,
  "stylometry_score": 0.6511
}
```

### Human-like example

```json
{
  "attribution": "likely_human",
  "confidence": 0.6246,
  "ai_likelihood": 0.1877,
  "combined_score": 0.1877,
  "llm_score": 0.12,
  "stylometry_score": 0.3133
}
```

### Borderline example

```json
{
  "attribution": "uncertain",
  "confidence": 0.0402,
  "ai_likelihood": 0.4799,
  "combined_score": 0.4799,
  "llm_score": 0.4,
  "stylometry_score": 0.6282
}
```

## Transparency Label Variants

The system returns one of three exact label variants.

### High-confidence AI / likely AI label

```text
This work shows strong signs of AI-generated text based on an automated multi-signal review. This label is not a final judgment of authorship and may be appealed by the creator.
```

### High-confidence human / likely human label

```text
This work shows strong signs of human authorship based on an automated multi-signal review. This label is not a guarantee, but the available signals support human authorship.
```

### Uncertain label

```text
This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided.
```

## `POST /appeal`

Required JSON body:

```json
{
  "content_id": "existing content id",
  "creator_reasoning": "creator explanation"
}
```

Example request:

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "acd20519-4054-4be6-bd13-c60016dbad2d", "creator_reasoning": "I wrote this myself and want a human review because formal or polished writing can look more AI-like than casual writing."}' | PYTHON_COLORS=0 python -m json.tool
```

Example response:

```json
{
  "appeal_id": "23d882b6-c62a-4ab2-8707-b93921d418c9",
  "content_id": "acd20519-4054-4be6-bd13-c60016dbad2d",
  "status": "under_review",
  "message": "Appeal received. This content has been marked for review."
}
```

If the `content_id` does not exist, the API returns:

```json
{
  "error": "No classification found for this content_id."
}
```

## Rate Limiting

The `/submit` endpoint is rate-limited with Flask-Limiter:

```text
10 per minute; 100 per day
```

The limit is applied to `/submit` because that endpoint calls an external LLM API and writes to the audit log. A normal creator may submit several pieces or retry a draft a few times, so `10 per minute` is enough for ordinary use. A script can easily flood the endpoint, so the per-minute limit catches abuse early. The daily limit caps sustained misuse and protects API cost.

### Rate-limit Test

Rate-limit test with 12 rapid requests:

```text
201
201
201
201
201
201
201
201
201
201
429
429
```

The final two requests were correctly rejected with HTTP `429`.

## Audit Log

Every classification and appeal is written to `audit_log.jsonl`. The log is JSONL, meaning each line is a separate JSON object.

Classification entries include:

- `event_type`
- `content_id`
- `creator_id`
- `timestamp`
- `attribution`
- `confidence`
- `ai_likelihood`
- `combined_score`
- `llm_score`
- `llm_reason`
- `stylometry_score`
- `stylometry_metrics`
- `label`
- `status`

Appeal entries include:

- `event_type`
- `appeal_id`
- `content_id`
- `creator_id`
- `timestamp`
- `original_attribution`
- `original_confidence`
- `original_ai_likelihood`
- `creator_reasoning`
- `status`

## Audit Log Example

This sample shows three classification events and one appeal event.

```jsonl
{"event_type": "classification_created", "content_id": "1e1ac5a9-8d91-47c4-9ef1-183502c70069", "creator_id": "test-ai", "timestamp": "2026-07-01T04:01:18.662278+00:00", "attribution": "likely_ai", "confidence": 0.4958, "ai_likelihood": 0.7479, "combined_score": 0.7479, "llm_score": 0.8, "llm_reason": "The text features generic phrasing, polished structure, and formulaic transitions, which are characteristic of AI-generated content. The language is also overly formal and lacks personal detail, suggesting a corporate or template-like style.", "stylometry_score": 0.6511, "stylometry_metrics": {"word_count": 43, "sentence_count": 3, "average_sentence_length": 14.3333, "sentence_length_variance": 29.5556, "type_token_ratio": 0.8837, "punctuation_density": 0.0159, "contraction_count": 0, "first_person_count": 0, "slang_count": 0, "all_caps_count": 1}, "label": "This work shows strong signs of AI-generated text based on an automated multi-signal review. This label is not a final judgment of authorship and may be appealed by the creator.", "status": "classified", "milestone_note": "M5 uses final transparency labels, two detection signals, and audit logging."}
{"event_type": "classification_created", "content_id": "9430fadb-dc64-426a-9d86-3aa91d2f0254", "creator_id": "test-human", "timestamp": "2026-07-01T04:01:23.118631+00:00", "attribution": "likely_human", "confidence": 0.6246, "ai_likelihood": 0.1877, "combined_score": 0.1877, "llm_score": 0.12, "llm_reason": "text features informal language, personal detail, and uneven rhythm, indicating a human-like writing style", "stylometry_score": 0.3133, "stylometry_metrics": {"word_count": 55, "sentence_count": 5, "average_sentence_length": 11.0, "sentence_length_variance": 45.2, "type_token_ratio": 0.8727, "punctuation_density": 0.0137, "contraction_count": 1, "first_person_count": 4, "slang_count": 2, "all_caps_count": 1}, "label": "This work shows strong signs of human authorship based on an automated multi-signal review. This label is not a guarantee, but the available signals support human authorship.", "status": "classified", "milestone_note": "M5 uses final transparency labels, two detection signals, and audit logging."}
{"event_type": "classification_created", "content_id": "acd20519-4054-4be6-bd13-c60016dbad2d", "creator_id": "test-borderline", "timestamp": "2026-07-01T04:01:27.640238+00:00", "attribution": "uncertain", "confidence": 0.0402, "ai_likelihood": 0.4799, "combined_score": 0.4799, "llm_score": 0.4, "llm_reason": "The text has a balanced and polished structure, but also includes a personal touch with 'I've been thinking a lot' and acknowledges complexity with 'genuine tradeoffs' and variability, which suggests a human-like perspective.", "stylometry_score": 0.6282, "stylometry_metrics": {"word_count": 39, "sentence_count": 3, "average_sentence_length": 13.0, "sentence_length_variance": 24.6667, "type_token_ratio": 0.8974, "punctuation_density": 0.0163, "contraction_count": 1, "first_person_count": 1, "slang_count": 0, "all_caps_count": 0}, "label": "This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided.", "status": "under_review", "milestone_note": "M5 uses final transparency labels, two detection signals, and audit logging."}
{"event_type": "appeal_submitted", "appeal_id": "23d882b6-c62a-4ab2-8707-b93921d418c9", "content_id": "acd20519-4054-4be6-bd13-c60016dbad2d", "creator_id": "test-borderline", "timestamp": "2026-07-01T04:02:12.547511+00:00", "original_attribution": "uncertain", "original_confidence": 0.0402, "original_ai_likelihood": 0.4799, "creator_reasoning": "I wrote this myself and want a human review because formal or polished writing can look more AI-like than casual writing.", "status": "under_review", "message": "Creator appealed the classification. Content is now under review."}
```

The third classification entry has `status: "under_review"` because it was appealed. The appeal appears as a separate `appeal_submitted` event linked by the same `content_id`.

## Known Limitations

The clearest false-positive risk is formal human writing. The LLM signal can treat polished, impersonal prose as AI-like because it looks generic or template-like. The stylometric signal can reinforce that mistake because academic, legal, policy, or professional writing often has regular sentence structure and limited informality markers.

The borderline remote-work example shows this uncertainty. The LLM score was `0.4`, while the stylometry score was `0.6282`. The signals did not fully agree, and the final `ai_likelihood` landed near the uncertain middle at `0.4799`. In that case, the uncertainty behavior worked correctly.

Short text is another weakness. Stylometric statistics such as sentence length variance and type-token ratio become unstable when there are only one or two sentences.

Edited AI text is also difficult. A human can revise AI output to add irregular phrasing, contractions, or personal detail, which may lower both signal scores.

If this were deployed for real, I would add persistent database storage, authentication for appeals, a larger labeled evaluation set, stronger calibration, and provenance evidence such as draft history or creator-attested writing process notes.

## Prototype Boundaries

This prototype does not prove authorship. It estimates authorship risk from two imperfect signals. It also does not authenticate creators, resolve appeals, or make moderation decisions. The appeal workflow only marks content as `under_review` and records creator reasoning for later human review.

## Spec Reflection

The spec helped by forcing the system to be multi-signal instead of relying on a single LLM classifier. That requirement shaped the architecture: signal functions produce separate scores, the score combiner merges them, the label generator translates the result, and the audit log records the whole decision. This made the pipeline easier to test and explain.

The implementation diverged from the early plan in one important way: I separated `ai_likelihood` from `confidence`. At first, it was tempting to treat the combined AI score itself as confidence. That would be misleading because a low AI score can still be a confident human classification. The final version uses `ai_likelihood` to show direction and `confidence` to show distance from the uncertain middle.

## AI Usage

I used AI assistance in several specific ways.

First, I used AI to translate the project requirements into a Flask architecture with `/submit`, `/appeal`, request validation, signal functions, score combination, labels, and audit logging. I revised the design by separating `ai_likelihood` from `confidence`, because using one number for both would make the output harder to interpret.

Second, I used AI to help generate the stylometric signal. The suggested metrics included sentence length variance, type-token ratio, punctuation density, contractions, first-person words, slang, and all-caps words. I kept the metrics but made sure the function returned both a single score and the underlying measurements so the audit log would be inspectable.

Third, I used AI during debugging. When `/submit` returned a JSON parsing error, the actual problem was a Flask traceback caused by a function signature mismatch. I fixed the mismatch by updating `attribution_from_combined_score` so its definition matched how it was called in `submit()`.

Fourth, I used AI to pressure-test the scoring logic. The formal and borderline examples exposed false-positive risk, so I documented that limitation instead of hiding it.

## Submission Checklist

- [x] `POST /submit` returns `content_id`, attribution, confidence, and label
- [x] Two detection signals are implemented and documented
- [x] Confidence scoring maps to `likely_ai`, `likely_human`, and `uncertain`
- [x] All three transparency label variants are written out exactly
- [x] `POST /appeal` captures creator reasoning
- [x] Appeal updates content status to `under_review`
- [x] Audit log records classifications and appeals
- [x] `/submit` is rate-limited
- [x] README includes real scoring examples and known limitations
- [ ] Portfolio walkthrough video recorded and linked