# Provenance Guard

Provenance Guard is a Flask API for text-authorship attribution. A user submits text, the system runs three detection signals, combines them into an AI-likelihood score and confidence score, returns a plain-language transparency label, stores the decision in SQLite, exposes audit events through `/log`, and gives creators a way to appeal.

The project is not designed to prove authorship. It is designed to make automated attribution decisions visible, explainable, appealable, and auditable.

## Project Status

| Milestone | Status | Evidence |
|---|---|---|
| M3 | Complete | `POST /submit`, first Groq LLM signal, `GET /log`, structured audit entries |
| M4 | Complete | three-signal ensemble, combined scoring, confidence scoring, calibration examples |
| M5 | Complete | final labels, `/appeal`, rate limiting, SQLite audit log |
| M6 | In progress | README complete |

## Problem

AI-text detection is risky because polished human writing can look machine-generated, and edited AI output can look human. A detector that simply says “AI” or “human” with no explanation creates a false sense of certainty.

Provenance Guard addresses this by combining multiple imperfect signals, returning `uncertain` when evidence is mixed, and allowing creators to appeal a classification. The goal is not an omniscient detector. The goal is a cautious transparency layer that records evidence and avoids pretending that surface-level authorship detection can prove who wrote something.

## Tech Stack

| Component | Tool |
|---|---|
| Backend API | Flask |
| LLM signal | Groq `llama-3.3-70b-versatile` |
| Structural signal | Pure-Python stylometric heuristics |
| Specificity signal | Pure-Python specificity/genericness heuristics |
| Rate limiting | Flask-Limiter |
| Persistence | SQLite |
| Analytics | Custom `/analytics` endpoint |
| Environment config | `python-dotenv` and `.env` for API key |

## Project Structure

```text
Provenance_Guard/
├── app.py              # Flask routes
├── detector.py         # three detection signals and score combination
├── storage.py          # SQLite persistence and audit events
├── labels.py           # transparency label text
├── analytics.py        # aggregate metrics for /analytics
├── planning.md         # architecture and implementation plan
├── README.md           # final project documentation
├── requirements.txt    # project dependencies
├── .gitignore          # excludes .env, .venv, cache files, database
└── data/
    └── provenance_guard.db  # generated locally, gitignored
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

For my local demo, the server runs at:

```text
http://localhost:5001
```

If your local `app.py` uses port `5000` instead, replace `5001` with `5000` in the curl commands below.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | health check |
| `POST` | `/submit` | classify submitted text |
| `POST` | `/appeal` | appeal a classification |
| `GET` | `/appeals` | list submitted appeals |
| `GET` | `/log` | return structured audit events |
| `GET` | `/analytics` | return aggregate classification and appeal metrics |
| `POST` | `/certificate` | create a creator-attested process certificate |

## Architecture

### Submission Flow

```text
Client
  |
  | POST /submit {text, creator_id, optional content_type}
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
Signal 3: Specificity / genericness checker
  | returns specificity_score + metrics
  v
Score combiner
  | returns ai_likelihood + signal_agreement + confidence
  v
Attribution mapper
  | likely_ai / likely_human / uncertain
  v
Transparency label generator
  |
  v
SQLite storage
  | stores classification record
  | writes classification_created audit event
  v
JSON response
```

### Appeal Flow

```text
Client
  |
  | POST /appeal {content_id, creator_id, creator_reasoning, optional_process_note}
  v
Input validation
  |
  v
Find original classification in SQLite
  |
  v
Update classification status to under_review
  |
  v
Create appeal record
  |
  v
Write appeal_submitted audit event
  |
  v
JSON confirmation
```

### Analytics Flow

```text
Client
  |
  | GET /analytics
  v
Read SQLite classifications + appeals
  |
  v
Calculate totals, averages, attribution counts, appeal count, appeal rate
  |
  v
JSON analytics response
```

### Certificate Flow

```text
Client
  |
  | POST /certificate {content_id, creator_id, verification_note}
  v
Find original classification
  |
  v
Create creator-attested process certificate
  |
  v
Write certificate_created audit event
  |
  v
JSON certificate response
```

## `POST /submit`

Classifies submitted writing and returns the attribution result.

Required JSON body:

```json
{
  "text": "Text to evaluate",
  "creator_id": "creator identifier"
}
```

Optional field:

```json
{
  "content_type": "essay"
}
```

Example request:

```bash
curl -s -X POST http://localhost:5001/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.", "creator_id": "test-ai", "content_type": "essay"}' | PYTHON_COLORS=0 python -m json.tool
```

Example response:

```json
{
  "ai_likelihood": 0.7618,
  "attribution": "uncertain",
  "confidence": 0.6195,
  "content_id": "e6698d36-810d-4006-b7cc-8d69aa50433e",
  "creator_id": "test-ai",
  "label": "This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided.",
  "signal_agreement": 0.7977,
  "signals": {
    "llm": {
      "reason": "The text features generic phrasing, polished structure, and formulaic transitions.",
      "score": 0.8
    },
    "specificity": {
      "metrics": {
        "abstract_noun_count": 3,
        "concrete_detail_count": 0,
        "first_person_count": 0,
        "formulaic_transition_count": 1,
        "generic_phrase_count": 4,
        "named_entity_proxy_count": 0,
        "sensory_word_count": 0,
        "time_or_place_marker_count": 0
      },
      "score": 0.845
    },
    "stylometry": {
      "metrics": {
        "all_caps_count": 0,
        "average_sentence_length": 14.3333,
        "contraction_count": 0,
        "first_person_count": 0,
        "long_sentence_ratio": 0.0,
        "punctuation_density": 0.0159,
        "sentence_count": 3,
        "sentence_length_variance": 29.5556,
        "short_sentence_ratio": 0.0,
        "type_token_ratio": 0.8837,
        "word_count": 43
      },
      "score": 0.6427
    }
  },
  "status": "classified"
}
```

Note: this example returns `uncertain` even though `ai_likelihood` is high because the conservative mapper requires both high AI-likelihood and high confidence. This is intentional false-positive protection.

## Detection Signals

The system uses three independent signals. Each signal returns a score from `0.0` to `1.0`.

```text
0.0 = strongly human-like
0.5 = mixed / unclear
1.0 = strongly AI-like
```

| Signal | What it measures | Why it helps | What it misses |
|---|---|---|---|
| Groq LLM classifier | Generic phrasing, formulaic structure, polished but impersonal tone, lack of specific lived detail | Captures whole-passage style and meaning better than hand-written rules | Can falsely flag polished, formal, academic, professional, or non-native-English human writing |
| Stylometric heuristics | Word count, sentence count, average sentence length, sentence length variance, type-token ratio, punctuation density, contractions, first-person language, all-caps words, short/long sentence ratios | Transparent, deterministic, cheap, and inspectable | Cannot understand meaning; weak on short text; formal human writing can look structurally AI-like |
| Specificity / genericness heuristics | Concrete detail, sensory words, first-person markers, named-entity proxy count, time/place markers, generic phrases, abstract nouns, formulaic transitions | Separates situated writing from generic template-like prose | AI can fake specificity; abstract human writing may be wrongly treated as generic |

### Signal 1: Groq LLM Classifier

The Groq signal asks `llama-3.3-70b-versatile` to classify whether the submitted text reads as AI-like or human-like. The prompt explicitly tells the model not to classify based on topic alone. Formal subject matter is not enough to call something AI-generated.

This signal is useful because it can notice broad patterns such as generic phrasing, overly smooth transitions, hedged structure, and a lack of concrete personal detail. Its weakness is that those same traits can appear in formal human writing.

### Signal 2: Stylometric Heuristic Checker

The stylometric signal computes structural features directly from the text. It checks word count, sentence count, average sentence length, sentence length variance, type-token ratio, punctuation density, contraction count, first-person count, all-caps count, short sentence ratio, and long sentence ratio.

This signal is useful because it is explainable. The audit log stores the exact metrics. Its weakness is that surface style is not authorship. A careful human writer may produce uniform prose, while edited AI text may include casual human-like irregularity.

### Signal 3: Specificity / Genericness Checker

The specificity signal measures whether the text contains concrete, situated detail or generic, abstract, formulaic language. It counts generic phrases such as “it is important to note,” formulaic transitions such as “furthermore,” abstract nouns such as “society” or “framework,” and concrete-detail proxies such as sensory words, first-person markers, time/place markers, and named-entity-like capitalized words.

This signal is useful because many AI-like submissions sound polished but unsituated. Its weakness is that specificity can be faked, and some legitimate human writing is abstract by genre.

## Confidence Scoring

The system reports three related values:

```text
ai_likelihood
signal_agreement
confidence
```

`ai_likelihood` is the direction of the evidence. A value near `1.0` means the signals lean AI-like. A value near `0.0` means the signals lean human-like. A value near `0.5` means the evidence is mixed or borderline.

`signal_agreement` measures whether the three signals point in the same direction.

```python
signal_agreement = 1 - (max(signal_scores) - min(signal_scores))
```

`confidence` measures how much the system should trust the classification. It combines distance from the uncertain middle with signal agreement.

```python
distance_from_middle = abs(ai_likelihood - 0.5) * 2

confidence = (0.65 * distance_from_middle) + (0.35 * signal_agreement)
```

The combined AI-likelihood score is computed with a weighted average:

```python
ai_likelihood = (0.50 * llm_score) + (0.30 * stylometry_score) + (0.20 * specificity_score)
```

Reasoning for weights:

- LLM signal gets 50% because it evaluates the whole passage.
- Stylometry gets 30% because it provides inspectable structural evidence.
- Specificity gets 20% because it captures genericness, but concrete detail can be faked.

## Classification Thresholds

The attribution mapper is deliberately conservative.

| Condition | Attribution |
|---|---|
| `ai_likelihood >= 0.75` and `confidence >= 0.65` | `likely_ai` |
| `ai_likelihood <= 0.30` and `confidence >= 0.65` | `likely_human` |
| everything else | `uncertain` |

This means a text can have high AI-likelihood but still return `uncertain` if confidence is not high enough. That is intentional. A false positive against a human creator is more harmful than letting a borderline case remain unresolved.

## Calibration Results

These are real local test results from the three-signal SQLite version.

| Test case | LLM score | Stylometry score | Specificity score | AI likelihood | Signal agreement | Confidence | Attribution |
|---|---:|---:|---:|---:|---:|---:|---|
| AI-like formal paragraph | 0.8000 | 0.6427 | 0.8450 | 0.7618 | 0.7977 | 0.6195 | `uncertain` |
| Casual human ramen review | 0.1400 | 0.3133 | 0.0000 | 0.1640 | 0.6867 | 0.6771 | `likely_human` |
| Borderline remote-work paragraph | 0.5000 | 0.6115 | 0.3333 | 0.5001 | 0.7218 | 0.2528 | `uncertain` |

The AI-like example shows the conservative design. It is AI-like, but confidence is just below the `0.65` threshold, so the system avoids the stronger `likely_ai` label. The casual human example is both low AI-likelihood and high enough confidence, so it returns `likely_human`. The borderline case remains `uncertain`.

## Transparency Label Variants

The system returns one of three exact label variants.

### `likely_ai`

```text
This work shows strong signs of AI-generated text based on an automated multi-signal review. This label is not a final judgment of authorship and may be appealed by the creator.
```

### `likely_human`

```text
This work shows strong signs of human authorship based on an automated multi-signal review. This label is not a guarantee, but the available signals support human authorship.
```

### `uncertain`

```text
This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided.
```

## `POST /appeal`

Allows a creator to contest a classification.

Required JSON body:

```json
{
  "content_id": "existing content id",
  "creator_id": "creator identifier",
  "creator_reasoning": "creator explanation"
}
```

Optional field:

```json
{
  "optional_process_note": "extra context about how the piece was written"
}
```

Example request:

```bash
curl -s -X POST http://localhost:5001/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "83a8177b-c19d-4ea2-929b-cfa1fdb65bf3", "creator_id": "test-borderline", "creator_reasoning": "I wrote this myself and want a human review because formal or polished writing can look more AI-like than casual writing.", "optional_process_note": "I drafted and revised this myself before submitting."}' | PYTHON_COLORS=0 python -m json.tool
```

Example response:

```json
{
  "appeal_id": "08d5091b-0ab2-4d69-8c69-ed9b58b84b30",
  "content_id": "83a8177b-c19d-4ea2-929b-cfa1fdb65bf3",
  "message": "Appeal received. This content has been marked for human review.",
  "status": "under_review"
}
```

If the `content_id` does not exist, the API returns:

```json
{
  "error": "No classification found for this content_id."
}
```

Automated reclassification is intentionally out of scope. An appeal introduces human review; it does not ask the detector to judge itself again.

## `GET /appeals`

Returns submitted appeals for reviewer inspection.

Example request:

```bash
curl -s http://localhost:5001/appeals | PYTHON_COLORS=0 python -m json.tool
```

Example response:

```json
{
  "appeals": [
    {
      "appeal_id": "08d5091b-0ab2-4d69-8c69-ed9b58b84b30",
      "content_id": "83a8177b-c19d-4ea2-929b-cfa1fdb65bf3",
      "created_at": "2026-07-01T05:01:42.649837+00:00",
      "creator_id": "test-borderline",
      "creator_reasoning": "I wrote this myself and want a human review because formal or polished writing can look more AI-like than casual writing.",
      "optional_process_note": "I drafted and revised this myself before submitting.",
      "status": "under_review"
    }
  ]
}
```

## `GET /analytics`

Returns aggregate metrics across classifications and appeals.

Example request:

```bash
curl -s http://localhost:5001/analytics | PYTHON_COLORS=0 python -m json.tool
```

Example response:

```json
{
  "appeal_count": 1,
  "appeal_rate": 0.3333,
  "average_ai_likelihood": 0.4753,
  "average_confidence": 0.5165,
  "false_positive_risk_note": "High-confidence AI labels require both high AI-likelihood (>= 0.75) and high confidence (>= 0.65).",
  "likely_ai_count": 0,
  "likely_human_count": 1,
  "most_common_attribution": "uncertain",
  "total_submissions": 3,
  "uncertain_count": 2
}
```

## `POST /certificate`

Creates a creator-attested process certificate. This is not proof of authorship. It records that the creator supplied additional process context.

Required JSON body:

```json
{
  "content_id": "existing content id",
  "creator_id": "creator identifier"
}
```

Optional field:

```json
{
  "verification_note": "Creator supplied a process note and requested review."
}
```

Example request:

```bash
curl -s -X POST http://localhost:5001/certificate \
  -H "Content-Type: application/json" \
  -d '{"content_id": "83a8177b-c19d-4ea2-929b-cfa1fdb65bf3", "creator_id": "test-borderline", "verification_note": "Creator supplied a process note and requested review."}' | PYTHON_COLORS=0 python -m json.tool
```

Example response:

```json
{
  "certificate_id": "4de60a33-8b7b-4f06-9ae0-bd8b20ea75dd",
  "certificate_label": "Creator-attested human process",
  "content_id": "83a8177b-c19d-4ea2-929b-cfa1fdb65bf3",
  "display_text": "The creator has submitted additional process context for this work. This certificate records a human authorship claim but does not independently prove authorship."
}
```

The certificate is deliberately modest. It does not say “verified human” because the system does not verify identity, draft history, timestamps, or external evidence.

## Rate Limiting

The `/submit` endpoint is rate-limited with Flask-Limiter:

```text
10 per minute; 100 per day
```

The limit is applied to `/submit` because that endpoint calls an external LLM API and writes to the database. A normal creator may submit several pieces or retry a draft a few times, so `10 per minute` is enough for ordinary use. A script can easily flood the endpoint, so the per-minute limit catches abuse early. The daily limit caps sustained misuse and protects API cost.

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

Audit events are stored in SQLite at:

```text
data/provenance_guard.db
```

`GET /log` returns the append-only audit trail as JSON.

Classification audit events include:

- `event_type`
- `content_id`
- `creator_id`
- `created_at`
- `attribution`
- `ai_likelihood`
- `confidence`
- `signal_agreement`
- `llm_score`
- `stylometry_score`
- `specificity_score`
- `status`

Appeal audit events include:

- `event_type`
- `appeal_id`
- `content_id`
- `creator_id`
- `created_at`
- `original_attribution`
- `original_ai_likelihood`
- `original_confidence`
- `creator_reasoning`
- `optional_process_note`
- `status`

Certificate audit events include:

- `event_type`
- `certificate_id`
- `content_id`
- `creator_id`
- `created_at`
- `certificate_label`

### `GET /log` Example

```json
{
  "entries": [
    {
      "content_id": "83a8177b-c19d-4ea2-929b-cfa1fdb65bf3",
      "created_at": "2026-07-01T05:07:52.987173+00:00",
      "creator_id": "test-borderline",
      "event_id": "b3f70fea-26ca-443f-880b-7c7f5687054b",
      "event_type": "classification_created",
      "payload": {
        "ai_likelihood": 0.5001,
        "attribution": "uncertain",
        "confidence": 0.2528,
        "llm_score": 0.5,
        "signal_agreement": 0.7218,
        "specificity_score": 0.3333,
        "status": "classified",
        "stylometry_score": 0.6115
      }
    },
    {
      "content_id": "09578989-4fa2-4841-8c39-24ff8542a21b",
      "created_at": "2026-07-01T05:07:47.324120+00:00",
      "creator_id": "test-human",
      "event_id": "093ffa42-abea-41f3-8a88-289db7f0e2ea",
      "event_type": "classification_created",
      "payload": {
        "ai_likelihood": 0.164,
        "attribution": "likely_human",
        "confidence": 0.6771,
        "llm_score": 0.14,
        "signal_agreement": 0.6867,
        "specificity_score": 0.0,
        "status": "classified",
        "stylometry_score": 0.3133
      }
    },
    {
      "content_id": "e6698d36-810d-4006-b7cc-8d69aa50433e",
      "created_at": "2026-07-01T05:07:36.242707+00:00",
      "creator_id": "test-ai",
      "event_id": "30cc7da6-35e1-495c-b42b-4c5cd678199d",
      "event_type": "classification_created",
      "payload": {
        "ai_likelihood": 0.7618,
        "attribution": "uncertain",
        "confidence": 0.6195,
        "llm_score": 0.8,
        "signal_agreement": 0.7977,
        "specificity_score": 0.845,
        "status": "classified",
        "stylometry_score": 0.6427
      }
    }
  ]
}
```

## Known Limitations

The system cannot prove authorship. It only evaluates surface evidence in text.

The clearest false-positive risk is formal human writing. The LLM signal can treat polished, impersonal prose as AI-like because it looks generic or template-like. The stylometric signal can reinforce that mistake because academic, legal, policy, or professional writing often has regular sentence structure and limited informality markers. The specificity signal can also penalize abstract writing that is legitimately human-authored.

The AI-like formal paragraph demonstrates the conservative design. It produced `ai_likelihood = 0.7618`, but confidence was `0.6195`, below the `0.65` threshold. The system therefore returned `uncertain` instead of `likely_ai`.

Short text is another weakness. Stylometric statistics such as sentence length variance and type-token ratio become unstable when there are only one or two sentences.

Edited AI text is difficult. A human can revise AI output to add irregular phrasing, contractions, or personal detail, which may lower the apparent AI-likelihood.

Non-native English writing is also a risk area. Direct, formal, or grammatically regular writing can be misread as AI-like, so the system avoids making strong claims unless the score and confidence thresholds are both met.

If this were deployed for real, I would add authentication for appeals, reviewer permissions, a larger labeled evaluation set, stronger calibration, and external provenance evidence such as draft history.

## Prototype Boundaries

This prototype does not prove authorship. It estimates authorship risk from three imperfect signals. It does not authenticate creators, resolve appeals, verify real-world identity, inspect document revision history, detect plagiarism, or make moderation decisions. The appeal workflow only marks content as `under_review` and records creator reasoning for later human review.

The certificate endpoint is also intentionally limited. It records a creator-attested process note, but it does not independently verify that claim.

## Spec Reflection

The spec helped by forcing the system to be multi-signal instead of relying on a single LLM classifier. That requirement shaped the architecture: signal functions produce separate scores, the score combiner merges them, the label generator translates the result, and the audit log records the decision.

The implementation changed after testing. The original version used two signals and a JSONL audit log. The final version uses a modular file structure, SQLite persistence, three detection signals, an analytics endpoint, and a certificate endpoint to match the full planning document.

The biggest design lesson was that `ai_likelihood` and `confidence` must remain separate. `ai_likelihood` says which direction the evidence points. `confidence` says how safe it is to trust that direction. Without that separation, the system would be more likely to overstate borderline results.

## AI Usage

I used AI assistance in several specific ways.

First, I used AI to translate the project requirements into a Flask architecture with `/submit`, `/appeal`, request validation, signal functions, score combination, labels, and audit logging. I revised the design to keep `ai_likelihood`, `signal_agreement`, and `confidence` separate.

Second, I used AI to help generate the stylometric and specificity heuristic functions. The stylometric metrics included sentence length variance, type-token ratio, punctuation density, contractions, first-person words, all-caps words, and short/long sentence ratios. The specificity metrics included generic phrases, formulaic transitions, abstract nouns, sensory words, time/place markers, first-person markers, and named-entity proxies.

Third, I used AI during debugging. When `/submit` returned parsing or traceback errors, I inspected whether the route was returning valid JSON and whether the function signatures matched their call sites. I also fixed command-line mistakes such as using blank lines after curl continuation backslashes.

Fourth, I used AI to pressure-test the scoring logic. The formal and borderline examples exposed false-positive risk, so I documented that limitation instead of hiding it.
