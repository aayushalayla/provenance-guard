# Provenance Guard Planning
This is a pre-implementation plan. 
README.md shows what was actually built and where the build diverged from this plan. 

## Project Overview

Provenance Guard is an authorship-transparency backend for creative sharing platforms. It analyzes submitted text and returns a structured attribution result: `likely_ai`, `likely_human`, or `uncertain`.

The system is not designed as a perfect AI detector. Perfect AI detection is not realistic, especially for short, edited, formal, hybrid, or genre-bending writing. 

Provenance Guard is designed as a transparency system: it surfaces evidence, communicates uncertainty, protects creators from overconfident false accusations, and gives creators a route to appeal.
---

## Design Thesis

The central design problem is not simply “is this AI-generated?” The harder problem is how a platform should behave when automated authorship evidence is imperfect.

A false positive is worse than a false negative in this setting. If the system labels a human creator’s work as AI-generated, it can damage trust, attribution, and reputation. Because of that, Provenance Guard requires both high AI-likeness and high confidence before returning a high-confidence AI label.

The system separates two concepts:

```text
ai_likelihood = how AI-like the submitted text appears
confidence = how much the system trusts that judgment
```

This matters because a text can look somewhat AI-like while still producing low confidence if the detection signals disagree.

Example:

```text
LLM score:          0.90
Stylometry score:   0.25
Specificity score:  0.30
```

A simple average might produce a middle score and hide the disagreement. Provenance Guard instead treats this as mixed evidence and returns `uncertain`.

---

## User Story

A creative writing platform wants to show readers a fair authorship-transparency label when someone posts written work.

A creator submits a poem, story excerpt, essay, caption, or blog post. The backend analyzes the writing using three signals. It returns a label that readers can understand without needing to inspect raw model scores.

If the creator believes the label is wrong, they can appeal. The appeal does not automatically reverse the decision. It changes the content status to `under_review`, stores the creator’s reasoning, and creates an audit trail for a human reviewer.

---

## System Scope

### In scope

The system will:

* accept text submissions
* validate required request fields
* run 3 detection signals
* return individual signal scores
* calculate AI-likeness
* calculate confidence
* map scores to an attribution category
* return a transparency label
* store decisions in SQLite
* expose recent audit events through `GET /log`
* accept creator appeals
* expose pending appeals through `GET /appeals`
* rate-limit the submission endpoint
* expose simple analytics through `GET /analytics`
* optionally issue a creator-attested provenance certificate through `POST /certificate`

### Out of scope

The system will not:

* prove authorship
* identify the exact AI model used
* detect plagiarism
* inspect Google Docs revision history
* verify real-world identity
* automatically reverse appealed classifications
* handle images, audio, or video
* moderate harmful content

---

## Technical Stack

```text
API framework:        Flask
LLM signal:           Groq, llama-3.3-70b-versatile
Heuristic signals:    Pure Python
Rate limiting:        Flask-Limiter
Persistence:          SQLite
Environment config:   python-dotenv
```

Required files:

```text
provenance-guard/
│
├── app.py
├── detector.py
├── storage.py
├── labels.py
├── analytics.py
├── requirements.txt
├── .gitignore
├── README.md
├── planning.md
└── data/
    └── provenance_guard.db
```

Reasoning for file separation:

* `app.py` handles Flask routes.
* `detector.py` handles detection signals and scoring.
* `storage.py` handles SQLite setup and audit logging.
* `labels.py` maps attribution results to label text.
* `analytics.py` calculates dashboard metrics.

This avoids turning the entire project into one giant file.

---

## Architecture

```text
SUBMISSION FLOW

Client / Creative Platform
   |
   | POST /submit
   | Body: text, creator_id, optional content_type
   v
Flask API
   |
   v
Request Validation
   |
   | rejects missing text, empty text, missing creator_id
   v
Content ID Generator
   |
   | creates UUID for submitted work
   v
Detection Pipeline
   |
   | passes raw text to all three signals
   |
   +--> Signal 1: Groq LLM Classifier
   |       input: text
   |       output: llm_score, llm_reason
   |
   +--> Signal 2: Stylometric Structure Signal
   |       input: text
   |       output: stylometry_score, metrics
   |
   +--> Signal 3: Specificity / Genericness Signal
           input: text
           output: specificity_score, metrics

Detection Pipeline
   |
   v
Score Combiner
   |
   | input: llm_score, stylometry_score, specificity_score
   | output: ai_likelihood, signal_agreement, confidence
   v
Attribution Mapper
   |
   | input: ai_likelihood + confidence
   | output: likely_ai / likely_human / uncertain
   v
Transparency Label Generator
   |
   | input: attribution
   | output: reader-facing label text
   v
SQLite Storage
   |
   | saves classification record
   | saves audit event
   v
JSON Response
   |
   | returns content_id, attribution, ai_likelihood,
   | confidence, label, signal scores, status
   v
Client displays label to reader
```

```text
APPEAL FLOW

Client / Creator
   |
   | POST /appeal
   | Body: content_id, creator_id, creator_reasoning,
   |       optional_process_note
   v
Flask API
   |
   v
Request Validation
   |
   | rejects missing content_id or creator_reasoning
   v
Find Original Classification
   |
   | looks up content_id in SQLite
   v
Status Update
   |
   | changes status from classified to under_review
   v
Appeal Record
   |
   | stores creator reasoning and optional process note
   v
Audit Log
   |
   | logs appeal_submitted event
   v
JSON Confirmation
   |
   | returns content_id, appeal_id, status, message
   v
Human reviewer can inspect appeal queue
```

```text
ANALYTICS FLOW

GET /analytics
   |
   v
Read SQLite classification + appeal records
   |
   v
Calculate:
   - total submissions
   - likely_ai count
   - likely_human count
   - uncertain count
   - appeal count
   - appeal rate
   - average confidence
   - average AI-likelihood
   - most common result
   |
   v
Return JSON dashboard summary
```

---

## API Surface

## `GET /`

Health check route.

### Response

```json
{
  "service": "Provenance Guard",
  "status": "running",
  "version": "1.0"
}
```

---

## `POST /submit`

Accepts a submitted piece of text and returns an attribution result.

### Request body

```json
{
  "text": "The submitted writing goes here.",
  "creator_id": "creator-123",
  "content_type": "short_story"
}
```

`content_type` is optional. The first implementation will accept it but will not use it heavily. Later, it could help the system interpret poetry, captions, essays, or fiction differently.

### Validation rules

The request is invalid if:

* body is not JSON
* `text` is missing
* `text` is empty or whitespace only
* `creator_id` is missing
* `creator_id` is empty or whitespace only

If validation fails, return HTTP `400`.

### Successful response

```json
{
  "content_id": "uuid-value",
  "creator_id": "creator-123",
  "attribution": "uncertain",
  "ai_likelihood": 0.58,
  "confidence": 0.42,
  "label": "This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided.",
  "signals": {
    "llm": {
      "score": 0.72,
      "reason": "The prose is polished and somewhat generic, but not conclusive."
    },
    "stylometry": {
      "score": 0.48,
      "metrics": {
        "word_count": 94,
        "sentence_count": 5,
        "average_sentence_length": 18.8,
        "sentence_length_variance": 9.2,
        "type_token_ratio": 0.73,
        "punctuation_density": 0.041,
        "contraction_count": 1,
        "first_person_count": 2
      }
    },
    "specificity": {
      "score": 0.43,
      "metrics": {
        "concrete_detail_count": 4,
        "generic_phrase_count": 1,
        "first_person_count": 2,
        "named_entity_proxy_count": 1,
        "sensory_word_count": 2
      }
    }
  },
  "status": "classified"
}
```

### Error response

```json
{
  "error": "Missing or invalid 'text'."
}
```

---

## `POST /appeal`

Allows a creator to contest a classification.

### Request body

```json
{
  "content_id": "uuid-value",
  "creator_id": "creator-123",
  "creator_reasoning": "I wrote this myself. It may sound formal because it was adapted from a class essay.",
  "optional_process_note": "I drafted it over two days and edited it before submission."
}
```

### Validation rules

The request is invalid if:

* body is not JSON
* `content_id` is missing
* `creator_id` is missing
* `creator_reasoning` is missing
* no classification exists for the submitted `content_id`

### Successful response

```json
{
  "appeal_id": "uuid-value",
  "content_id": "uuid-value",
  "status": "under_review",
  "message": "Appeal received. This content has been marked for human review."
}
```

### Error response

```json
{
  "error": "No classification found for this content_id."
}
```

---

## `GET /log`

Returns recent structured audit events.

### Response

```json
{
  "entries": [
    {
      "event_id": "uuid-value",
      "event_type": "classification_created",
      "content_id": "uuid-value",
      "creator_id": "creator-123",
      "created_at": "2026-06-30T15:22:10Z",
      "payload": {
        "attribution": "uncertain",
        "ai_likelihood": 0.58,
        "confidence": 0.42,
        "llm_score": 0.72,
        "stylometry_score": 0.48,
        "specificity_score": 0.43,
        "status": "classified"
      }
    }
  ]
}
```

---

## `GET /appeals`

Returns appeal records for reviewer inspection.

### Response

```json
{
  "appeals": [
    {
      "appeal_id": "uuid-value",
      "content_id": "uuid-value",
      "creator_id": "creator-123",
      "creator_reasoning": "I wrote this myself. It may sound formal because it was adapted from a class essay.",
      "optional_process_note": "I drafted it over two days and edited it before submission.",
      "status": "under_review",
      "created_at": "2026-06-30T15:25:10Z"
    }
  ]
}
```

---

## `GET /analytics`

Stretch feature.

Returns aggregate detection and appeal metrics.

### Response

```json
{
  "total_submissions": 12,
  "likely_ai_count": 3,
  "likely_human_count": 4,
  "uncertain_count": 5,
  "appeal_count": 2,
  "appeal_rate": 0.17,
  "average_ai_likelihood": 0.56,
  "average_confidence": 0.61,
  "most_common_attribution": "uncertain",
  "false_positive_risk_note": "High-confidence AI labels require both high AI-likelihood and high confidence."
}
```

---

## `POST /certificate`

Stretch feature.

Creates a creator-attested provenance certificate. This is not proof of authorship. It records that the creator supplied additional process context.

### Request body

```json
{
  "content_id": "uuid-value",
  "creator_id": "creator-123",
  "verification_note": "Creator supplied a process note and requested review."
}
```

### Response

```json
{
  "certificate_id": "uuid-value",
  "content_id": "uuid-value",
  "certificate_label": "Creator-attested human process",
  "display_text": "The creator has submitted additional process context for this work. This certificate records a human authorship claim but does not independently prove authorship."
}
```

This wording is intentionally modest. The system cannot honestly claim “verified human” unless it checks revision history, identity, timestamps, or external evidence.

---

## Detection Pipeline

The system uses an ensemble of three distinct signals. Each signal returns a score from `0.0` to `1.0`.

```text
0.0 = strongly human-like
0.5 = mixed / unclear
1.0 = strongly AI-like
```

The three signals measure different properties of the text:

```text
Signal 1: semantic/stylistic judgment
Signal 2: structural writing patterns
Signal 3: specificity vs genericness
```

This is stronger than using two near-duplicate signals because each signal looks at a different kind of evidence.

---

## Signal 1: Groq LLM Classifier

### Purpose

The Groq LLM classifier evaluates the text holistically. It looks for broad stylistic and semantic patterns that may suggest AI generation or human authorship.

### What it measures

The LLM signal measures:

* generic phrasing
* polished but bland structure
* formulaic transitions
* lack of personal detail
* repetitive “balanced” paragraph shape
* overuse of cautious or corporate-sounding language
* lack of friction, surprise, or idiosyncratic voice
* human-like messiness, specificity, or unevenness

### Prompt design principle

The classifier prompt must not ask whether the topic sounds like something AI might write about. It should classify writing style, not subject matter.

Bad prompt:

```text
Does this text discuss AI-like topics?
```

Better prompt:

```text
Analyze the writing style for AI-likeness. Do not classify based on topic alone. Formal or academic subject matter is not enough for a high AI score.
```

### Expected function output

```json
{
  "score": 0.72,
  "reason": "The prose is polished and generic, but contains some concrete details that reduce certainty."
}
```

### Blind spots

The LLM signal may fail when:

* a human writes formally
* a non-native English speaker writes in direct, structured prose
* a human edits heavily and removes messiness
* AI output is rewritten by a human
* the sample is too short
* the text intentionally imitates a genre
* the writing uses a generic topic but was still human-written

### Why it is still useful

The LLM signal can catch patterns that simple metrics miss. It can evaluate tone, semantic genericness, and whether the text feels templated.

---

## Signal 2: Stylometric Structure Signal

### Purpose

The stylometric signal measures visible structural properties of the writing using pure Python.

### What it measures

Metrics:

```text
word_count
sentence_count
average_sentence_length
sentence_length_variance
type_token_ratio
punctuation_density
contraction_count
first_person_count
all_caps_count
short_sentence_ratio
long_sentence_ratio
```

### Interpretation

AI-like structural patterns may include:

* very even sentence length
* few fragments
* low punctuation irregularity
* few contractions
* few first-person markers
* moderate-to-high average sentence length
* polished grammar with little variation

Human-like structural patterns may include:

* uneven sentence length
* fragments
* slang
* contractions
* first-person language
* all-caps emphasis
* irregular punctuation
* abrupt shifts in sentence rhythm

### Expected function output

```json
{
  "score": 0.48,
  "metrics": {
    "word_count": 94,
    "sentence_count": 5,
    "average_sentence_length": 18.8,
    "sentence_length_variance": 9.2,
    "type_token_ratio": 0.73,
    "punctuation_density": 0.041,
    "contraction_count": 1,
    "first_person_count": 2,
    "all_caps_count": 0,
    "short_sentence_ratio": 0.2,
    "long_sentence_ratio": 0.0
  }
}
```

### Blind spots

Stylometry may fail when:

* human writing is polished
* academic prose is intentionally formal
* poetry uses repetition and fragments
* very short samples produce unstable metrics
* AI text has been edited to add casual markers
* genre conventions distort sentence length and punctuation

### Why it is useful

This signal is independent from the LLM. It gives the system measurable evidence that can be shown in the response and logged.

---

## Signal 3: Specificity / Genericness Signal

### Purpose

The specificity signal measures whether the text contains concrete, situated, human-like detail or generic, abstract, formulaic language.


### What it measures

Metrics:

```text
concrete_detail_count
sensory_word_count
first_person_count
named_entity_proxy_count
time_or_place_marker_count
generic_phrase_count
abstract_noun_count
formulaic_transition_count
```

Concrete detail examples:

```text
yesterday
Queens
my friend
the ramen place
three hours
the blue mug
on the porch
after class
```

Generic phrase examples:

```text
it is important to note
in today's society
plays a crucial role
various stakeholders
ethical implications
transformative paradigm shift
responsible deployment
in conclusion
```

Formulaic transition examples:

```text
furthermore
moreover
in addition
therefore
consequently
overall
```

### Scoring logic

Specific, situated detail lowers AI-likeness.

Generic, abstract, formulaic language raises AI-likeness.

Expected function output:

```json
{
  "score": 0.43,
  "metrics": {
    "concrete_detail_count": 4,
    "sensory_word_count": 2,
    "first_person_count": 2,
    "named_entity_proxy_count": 1,
    "time_or_place_marker_count": 1,
    "generic_phrase_count": 1,
    "abstract_noun_count": 5,
    "formulaic_transition_count": 1
  }
}
```

### Blind spots

This signal may fail when:

* a human writes abstract theory or academic prose
* AI output includes fake concrete details
* fiction contains invented specificity
* personal essays are edited into a general style
* short texts lack enough detail for measurement

### Why it is useful

This signal adds a third kind of evidence. It looks at specificity, not just polish or sentence structure.

---

## Score Combination

The system calculates three values:

```text
ai_likelihood
signal_agreement
confidence
```

### Step 1: AI-likelihood

```text
ai_likelihood =
    (0.50 * llm_score)
  + (0.30 * stylometry_score)
  + (0.20 * specificity_score)
```

Reasoning:

* LLM gets 50% because it can evaluate style and meaning holistically.
* Stylometry gets 30% because structural uniformity is useful but brittle.
* Specificity gets 20% because genericness matters, but it can be faked.

### Step 2: Signal agreement

```text
signal_spread = max(signal_scores) - min(signal_scores)

signal_agreement = 1 - signal_spread
```

High agreement means the signals point in the same direction. Low agreement means the system should be more cautious.

Example:

```text
scores = [0.80, 0.76, 0.72]
signal_spread = 0.08
signal_agreement = 0.92
```

Example with disagreement:

```text
scores = [0.90, 0.25, 0.30]
signal_spread = 0.65
signal_agreement = 0.35
```

### Step 3: Confidence

```text
distance_from_middle = abs(ai_likelihood - 0.5) * 2

confidence =
    (0.65 * distance_from_middle)
  + (0.35 * signal_agreement)
```

Interpretation:

* A result far from 0.5 is more confident.
* Signals agreeing with each other raises confidence.
* Signals disagreeing lowers confidence.

Confidence is rounded to 4 decimal places.

### Why confidence is not the same as AI-likelihood

`ai_likelihood` answers:

```text
How AI-like does this text appear?
```

`confidence` answers:

```text
How much should the system trust that classification?
```

This prevents overconfident labels when evidence is mixed.

---

## Attribution Mapping

The system maps `ai_likelihood` and `confidence` to attribution categories.

```text
likely_ai:
    ai_likelihood >= 0.75
    AND confidence >= 0.65

likely_human:
    ai_likelihood <= 0.30
    AND confidence >= 0.65

uncertain:
    everything else
```

This is intentionally conservative. A high AI label requires both high AI-likeness and high confidence.

Examples:

```text
ai_likelihood = 0.82
confidence = 0.78
result = likely_ai
```

```text
ai_likelihood = 0.18
confidence = 0.71
result = likely_human
```

```text
ai_likelihood = 0.82
confidence = 0.42
result = uncertain
reason = AI-likeness is high, but signal agreement is weak
```

```text
ai_likelihood = 0.55
confidence = 0.30
result = uncertain
reason = close to middle
```

---

## Transparency Label Design

The label must be plain-language, non-accusatory, and honest about uncertainty.

The label returned by `POST /submit` must be one of the following exact strings.

| Attribution    | Label text                                                                                                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `likely_ai`    | "This work shows strong signs of AI-generated text based on an automated multi-signal review. This label is not a final judgment of authorship and may be appealed by the creator."     |
| `likely_human` | "This work shows strong signs of human authorship based on an automated multi-signal review. This label is not a guarantee, but the available signals support human authorship."        |
| `uncertain`    | "This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided." |

### Why these labels are designed this way

The `likely_ai` label avoids saying “this is AI-generated.” It says “shows strong signs,” which is more accurate.

The `likely_human` label avoids saying “verified human.” It says the available signals support human authorship.

The `uncertain` label does not hide uncertainty. It explicitly tells readers that the evidence is mixed or limited.

---

## Appeals Workflow

Creators can appeal any classification.

### Appeal request fields

Required:

```text
content_id
creator_id
creator_reasoning
```

Optional:

```text
optional_process_note
```

The optional process note lets creators explain context such as:

* “This was adapted from a class essay.”
* “I am a non-native English speaker.”
* “This is a poem, so repetition is intentional.”
* “I revised this heavily before posting.”
* “I used grammar-checking software but wrote the draft myself.”

### Appeal behavior

When an appeal is submitted:

1. Validate request body.
2. Look up original classification by `content_id`.
3. Verify that the classification exists.
4. Create an `appeal_id`.
5. Save appeal reasoning.
6. Update classification status to `under_review`.
7. Write an `appeal_submitted` audit event.
8. Return a confirmation response.

### Appeal status values

```text
under_review
resolved_upheld
resolved_changed
```

Only `under_review` is required for the first implementation. The resolved statuses are included so the design can grow later.

### Reviewer view

A human reviewer should be able to see:

* appeal ID
* content ID
* creator ID
* original attribution
* original AI-likelihood
* original confidence
* all signal scores
* label shown to readers
* creator reasoning
* optional process note
* current status
* timestamps

---

## Rate Limiting Plan

The `POST /submit` endpoint will use Flask-Limiter.

Chosen limits:

```text
10 submissions per minute
100 submissions per day
```

Reasoning:

A normal creator might submit a few drafts or test several pieces of writing. They are unlikely to submit more than 10 pieces in one minute. A script or adversarial user could flood the endpoint rapidly, especially if Groq calls are involved. The per-minute limit blocks bursts. The daily limit prevents sustained abuse while still allowing normal testing.

The rate limit applies to:

```text
POST /submit
```

Initial implementation:

```python
@limiter.limit("10 per minute;100 per day")
```

Expected error response:

```json
{
  "error": "Rate limit exceeded. Please try again later."
}
```

The appeal endpoint will not be rate-limited in the first class version, but a real platform should rate-limit appeals too.

---

## SQLite Persistence Plan

The system will use SQLite instead of an in-memory list so logs survive server restarts.

Database file:

```text
data/provenance_guard.db
```

### `classifications` table

```text
content_id TEXT PRIMARY KEY
creator_id TEXT NOT NULL
text_preview TEXT NOT NULL
content_type TEXT
attribution TEXT NOT NULL
ai_likelihood REAL NOT NULL
confidence REAL NOT NULL
llm_score REAL NOT NULL
stylometry_score REAL NOT NULL
specificity_score REAL NOT NULL
label TEXT NOT NULL
status TEXT NOT NULL
created_at TEXT NOT NULL
```

### `appeals` table

```text
appeal_id TEXT PRIMARY KEY
content_id TEXT NOT NULL
creator_id TEXT NOT NULL
creator_reasoning TEXT NOT NULL
optional_process_note TEXT
status TEXT NOT NULL
created_at TEXT NOT NULL
```

### `audit_events` table

```text
event_id TEXT PRIMARY KEY
event_type TEXT NOT NULL
content_id TEXT
creator_id TEXT
payload_json TEXT NOT NULL
created_at TEXT NOT NULL
```

### `certificates` table

```text
certificate_id TEXT PRIMARY KEY
content_id TEXT NOT NULL
creator_id TEXT NOT NULL
certificate_label TEXT NOT NULL
display_text TEXT NOT NULL
verification_note TEXT
created_at TEXT NOT NULL
```

---

## Audit Log Plan

Every classification and appeal creates an audit event.

### Classification audit payload

```json
{
  "event_type": "classification_created",
  "content_id": "uuid-value",
  "creator_id": "creator-123",
  "attribution": "uncertain",
  "ai_likelihood": 0.58,
  "confidence": 0.42,
  "llm_score": 0.72,
  "stylometry_score": 0.48,
  "specificity_score": 0.43,
  "label": "This work could not be classified with high confidence. The system found mixed or limited evidence, so readers should treat authorship as unresolved unless more context is provided.",
  "status": "classified"
}
```

### Appeal audit payload

```json
{
  "event_type": "appeal_submitted",
  "appeal_id": "uuid-value",
  "content_id": "uuid-value",
  "creator_id": "creator-123",
  "creator_reasoning": "I wrote this myself. It may sound formal because it was adapted from a class essay.",
  "optional_process_note": "I drafted it over two days and edited it before submission.",
  "status": "under_review"
}
```

### Certificate audit payload

```json
{
  "event_type": "certificate_created",
  "certificate_id": "uuid-value",
  "content_id": "uuid-value",
  "creator_id": "creator-123",
  "certificate_label": "Creator-attested human process"
}
```

The README will include at least three audit-log entries from real local testing.

---

## False Positive Protection

False positives are the main product risk.

The system reduces false positives in four ways:

1. The high-confidence AI label requires `ai_likelihood >= 0.75`.
2. The high-confidence AI label also requires `confidence >= 0.65`.
3. Signal disagreement lowers confidence.
4. Creators can appeal any classification.

Example false-positive scenario:

A human writer submits a formal academic paragraph.

Possible scores:

```text
llm_score = 0.80
stylometry_score = 0.72
specificity_score = 0.35
ai_likelihood = 0.686
confidence = 0.53
```

Result:

```text
uncertain
```

Reason:

The text is somewhat AI-like, but the system does not have enough confidence to make a high-confidence AI claim.

---

## Anticipated Edge Cases

### Edge Case 1: Very short text

Example:

```text
I love this poem.
```

Problem:

There are not enough words for stable stylometric or specificity metrics.

Expected handling:

Return `uncertain`.

---

### Edge Case 2: Formal human writing

Example:

```text
The relationship between monetary policy and asset price inflation has been extensively studied in the literature.
```

Problem:

Formal human writing looks polished, generic, and low in any personal markers.

Expected handling:

Usually `uncertain`, not `likely_ai`, unless all signals strongly agree.

---

### Edge Case 3: Poetry

Example:

```text
blue blue blue
the room remembers
what I won't
```

Problem:

Repetition, fragments, and unusual structure can confuse stylometry.

Expected handling:

The system should avoid high confidence when sentence structure is unusual.

---

### Edge Case 4: Edited AI text

Problem:

AI text can be edited to add personal details, contractions, and sentence variation.

Expected handling:

The system may return `uncertain` or `likely_human`. This is an accepted limitation.

---

### Edge Case 5: Non-native English writing

Problem:

Direct or formal phrasing may be wrongly treated as AI-like.

Expected handling:

The uncertainty threshold and appeal process should reduce harm.

---

### Edge Case 6: Hybrid authorship

Problem:

The creator may have written the text with AI assistance, grammar tools, or partial rewriting.

Expected handling:

The system should label visible evidence only. It should not claim certainty about the full writing process.

---

## Testing Plan

I will test at least six inputs.

### Test 1: Clearly AI-like

Input:

```text
Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.
```

Expected result:

```text
likely_ai or uncertain-high-ai-likelihood
```

Reason:

This uses generic AI-coded phrasing: “transformative paradigm shift,” “important to note,” “ethical implications,” “stakeholders,” and “responsible deployment.”

---

### Test 2: Clearly human-like casual writing

Input:

```text
ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there
```

Expected result:

```text
likely_human
```

Reason:

The text has first-person perspective, casual syntax, concrete detail, and uneven rhythm.

---

### Test 3: Borderline formal human writing

Input:

```text
The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.
```

Expected result:

```text
uncertain
```

Reason:

The text is formal and polished but not necessarily AI-generated.

---

### Test 4: Borderline edited AI-like writing

Input:

```text
I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type.
```

Expected result:

```text
uncertain
```

Reason:

It has some personal phrasing, but it is also balanced and general.

---

### Test 5: Short text

Input:

```text
I liked it.
```

Expected result:

```text
uncertain
```

Reason:

Too short for reliable classification.

---

### Test 6: Poetic / experimental text

Input:

```text
The window kept the rain like a secret. I kept my coat on indoors. Nobody asked why.
```

Expected result:

```text
uncertain or likely_human
```

Reason:

It has concrete imagery but short literary structure. The system should not overfit to sentence fragments.

---

## Success Criteria

The project is successful if:

* `POST /submit` returns structured JSON.
* The response includes `content_id`, `attribution`, `ai_likelihood`, `confidence`, `label`, `signals`, and `status`.
* All three signal scores are visible.
* `confidence` changes meaningfully across test cases.
* At least one input returns `likely_ai`.
* At least one input returns `likely_human`.
* At least one input returns `uncertain`.
* `POST /appeal` changes status to `under_review`.
* `GET /log` shows classification and appeal events.
* Rate limiting produces a `429` response after repeated submissions.
* `GET /analytics` returns aggregate project metrics.
* README includes evidence from real tests.

---

## README Evidence Plan

The README will include:

* Architecture overview
* Endpoint list
* Detection signals and what each captures
* What each signal misses
* Confidence scoring formula
* Explanation of `ai_likelihood` vs `confidence`
* Exact transparency labels
* Example high-confidence or high-AI-likelihood submission
* Example lower-confidence or uncertain submission
* Appeal workflow evidence
* Rate-limit configuration and reasoning
* Rate-limit test output
* Audit-log sample with at least three entries
* Analytics endpoint sample
* Certificate endpoint sample if completed
* Known limitations
* Spec reflection
* AI usage section

---

## AI Tool Plan

## M3: Submission Endpoint and First Signal

### Spec sections to provide to AI tool

* Project Overview
* Architecture
* API Surface
* Signal 1: Groq LLM Classifier
* SQLite Persistence Plan
* Audit Log Plan

### What I will ask it to generate

I will ask for:

* Flask app skeleton
* `GET /` health route
* `POST /submit` route with validation
* placeholder detector response first
* Groq signal function
* SQLite initialization
* classification insert function
* audit event insert function
* `GET /log` route

### What I will verify

I will test:

* invalid JSON returns `400`
* missing text returns `400`
* missing creator ID returns `400`
* valid submission returns `201`
* response includes `content_id`
* database stores classification
* `GET /log` returns the audit entry

---

## M4: Ensemble Signals and Scoring

### Spec sections to provide to AI tool

* Detection Pipeline
* Signal 2: Stylometric Structure Signal
* Signal 3: Specificity / Genericness Signal
* Score Combination
* Attribution Mapping
* Testing Plan

### What I will ask it to generate

I will ask for:

* stylometric signal function
* specificity signal function
* `combine_scores()` function
* `map_attribution()` function
* test helper that prints individual scores

### What I will verify

I will test all six planned inputs and inspect:

* individual signal scores
* `ai_likelihood`
* `signal_agreement`
* `confidence`
* final attribution

---

## M5: Production Layer

### Spec sections to provide to AI tool

* Transparency Label Design
* Appeals Workflow
* Rate Limiting Plan
* Audit Log Plan
* README Evidence Plan

### What I will ask it to generate

I will ask for:
* label generation function
* `POST /appeal`
* `GET /appeals`
* Flask-Limiter setup
* custom `429` error response
* status update logic
* appeal audit event logic

### What I will verify

I will test:

* all three label variants are reachable
* appeal creates an appeal record
* appeal updates classification status
* appeal appears in `GET /log`
* `GET /appeals` shows pending appeals
* repeated submit requests trigger `429`

---
## Additonal Features 

### Analytics Dashboard

Endpoint:

```text
GET /analytics
```

Metrics:

* total submissions
* likely AI count
* likely human count
* uncertain count
* appeal count
* appeal rate
* average AI-likelihood
* average confidence
* most common attribution
* README will include a sample `/analytics` response.

### Stretch 3: Provenance Certificate

Endpoint:

```text
POST /certificate
```

The certificate will be called:

```text
Creator-attested human process
```

It will not be called “verified human” unless the system actually verifies external evidence.

Documentation requirement:

* README will explain what the certificate does and does not prove.
* README will include a sample certificate response.

---

## Known Limitations

The system only evaluates surface evidence in text.

The system will struggle with:

* short submissions
* poetry
* experimental prose
* formal human writing
* non-native English writing
* hybrid human-AI writing
* heavily edited AI output
* human writing that intentionally imitates AI style
* AI writing that includes fake personal details
* resubmitted writing 

The system’s value is not certainty. Its value is structured evidence, uncertainty-aware labeling, and appealability.

If the ways in which a text is being classified as AI or Humam-like are explained in the code, someone can adjust their writing to curb the criteria. 
---

## Implementation Order

I will build in this order:

1. Create `planning.md`.
2. Create minimal `app.py`.
3. Add health route.
4. Add SQLite setup in `storage.py`.
5. Add placeholder `POST /submit`.
6. Add audit logging.
7. Add Groq signal.
8. Add stylometric signal.
9. Add specificity signal.
10. Add score combiner.
11. Add label generator.
12. Add `POST /appeal`.
13. Add `GET /appeals`.
14. Add Flask-Limiter.
15. Add `GET /analytics`.
16. Add `POST /certificate`.
17. Run tests with six inputs.
18. Add it to my README as evidence.

---

## Spec Reflection Plan

In the README, I will explain:

1. One way the spec helped:
   * The spec separated `ai_likelihood` from `confidence`, which made the implementation more careful about uncertainty.

2. One way implementation changed:

   * If I adjust signal weights or thresholds after testing, I will document why. 
   * If Groq API access fails, I will document the fallback placeholder behavior and explain how that limits the demo.

---

## AI Usage Plan
Planned AI use 1:

```text
I will ask AI to generate the initial Flask route structure from my API Surface and Architecture sections. I will revise the generated code to match my exact response fields and validation rules.
```

Planned AI use 2:

```text
I will ask AI to generate the stylometric and specificity heuristic functions from my Detection Pipeline section. I will revise the metrics and thresholds manually after testing against my six planned examples.
```

Planned AI use 3:

```text
I will ask AI to help draft README explanations after the code works. I will revise the README to include my actual test outputs instead of generic examples.
```
