"""
detector.py

Three independent detection signals plus score combination logic.

Signal 1: Groq LLM classifier      - semantic / stylistic judgment
Signal 2: Stylometric heuristics   - structural writing patterns
Signal 3: Specificity/genericness  - concrete detail vs formulaic language

Each signal returns a score from 0.0 (strongly human-like) to 1.0
(strongly AI-like). Signals are combined into ai_likelihood, and the
spread between signals feeds a signal_agreement term that in turn
feeds confidence, per planning.md.
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def clamp_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Signal 1: Groq LLM Classifier
# ---------------------------------------------------------------------------

def llm_signal(text):
    """
    Semantic / stylistic judgment. Returns {"score": float, "reason": str}.
    """

    if groq_client is None:
        return {
            "score": 0.5,
            "reason": "Groq signal unavailable because GROQ_API_KEY is not set. Using neutral placeholder score.",
        }

    system_prompt = """
You are an authorship-transparency classifier.

Your task is to evaluate whether a submitted text appears AI-generated or
human-written based on writing STYLE, not topic.

Do not classify based on subject matter alone. Formal or academic subject
matter is not enough to call something AI-generated.

Return JSON only with this exact shape:
{
  "score": 0.0,
  "reason": "brief explanation"
}

Score meaning:
0.0 to 0.24 = strongly human-like
0.25 to 0.44 = somewhat human-like
0.45 to 0.55 = uncertain or mixed
0.56 to 0.74 = somewhat AI-like
0.75 to 1.0 = strongly AI-like

AI-like signs: generic phrasing, polished but bland structure, formulaic
transitions, lack of personal detail, balanced "corporate" tone, absence
of friction or idiosyncratic voice.

Human-like signs: concrete personal detail, uneven rhythm, idiosyncratic
phrasing, slang, small imperfections, specific lived context.
""".strip()

    user_prompt = f"Analyze this text for AI-likeness.\n\nText:\n{text}"

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        return {
            "score": clamp_score(parsed.get("score")),
            "reason": str(parsed.get("reason", "No reason provided.")),
        }
    except Exception as error:
        return {
            "score": 0.5,
            "reason": f"Groq signal failed. Using neutral placeholder score. Error: {error}",
        }


# ---------------------------------------------------------------------------
# Signal 2: Stylometric Structure Signal
# ---------------------------------------------------------------------------

def stylometry_signal(text):
    """
    Structural writing patterns. Returns {"score": float, "metrics": dict}.
    """

    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"\b[\w']+\b", text.lower())
    punctuation_marks = re.findall(r"[.,!?;:]", text)

    if not words:
        return {
            "score": 0.5,
            "metrics": {
                "word_count": 0, "sentence_count": 0, "average_sentence_length": 0,
                "sentence_length_variance": 0, "type_token_ratio": 0,
                "punctuation_density": 0, "contraction_count": 0,
                "first_person_count": 0, "all_caps_count": 0,
                "short_sentence_ratio": 0, "long_sentence_ratio": 0,
            },
        }

    word_count = len(words)
    sentence_count = max(1, len(sentences))

    sentence_lengths = [
        len(re.findall(r"\b[\w']+\b", s.lower())) for s in sentences
    ] or [word_count]

    average_sentence_length = word_count / sentence_count

    if len(sentence_lengths) > 1:
        mean_len = sum(sentence_lengths) / len(sentence_lengths)
        sentence_length_variance = sum((l - mean_len) ** 2 for l in sentence_lengths) / len(sentence_lengths)
    else:
        sentence_length_variance = 0

    type_token_ratio = len(set(words)) / word_count
    punctuation_density = len(punctuation_marks) / max(1, len(text))

    contractions = re.findall(r"\b\w+'\w+\b", text.lower())
    first_person = re.findall(r"\b(i|me|my|mine|we|us|our|ours)\b", text.lower())
    all_caps_words = re.findall(r"\b[A-Z]{2,}\b", text)

    short_sentences = [l for l in sentence_lengths if l <= 5]
    long_sentences = [l for l in sentence_lengths if l >= 25]
    short_sentence_ratio = len(short_sentences) / len(sentence_lengths)
    long_sentence_ratio = len(long_sentences) / len(sentence_lengths)

    uniformity_score = 1.0 - min(sentence_length_variance / 50, 1.0)
    long_sentence_score = min(average_sentence_length / 25, 1.0)
    low_informality_score = 1.0 - min(
        (len(contractions) + len(first_person) + len(all_caps_words)) / 5, 1.0
    )
    vocab_score = min(type_token_ratio, 1.0)

    score = (
        0.30 * uniformity_score
        + 0.25 * long_sentence_score
        + 0.25 * low_informality_score
        + 0.20 * vocab_score
    )

    return {
        "score": round(score, 4),
        "metrics": {
            "word_count": word_count,
            "sentence_count": len(sentences),
            "average_sentence_length": round(average_sentence_length, 4),
            "sentence_length_variance": round(sentence_length_variance, 4),
            "type_token_ratio": round(type_token_ratio, 4),
            "punctuation_density": round(punctuation_density, 4),
            "contraction_count": len(contractions),
            "first_person_count": len(first_person),
            "all_caps_count": len(all_caps_words),
            "short_sentence_ratio": round(short_sentence_ratio, 4),
            "long_sentence_ratio": round(long_sentence_ratio, 4),
        },
    }


# ---------------------------------------------------------------------------
# Signal 3: Specificity / Genericness Signal
# ---------------------------------------------------------------------------

GENERIC_PHRASES = [
    "it is important to note", "in today's society", "plays a crucial role",
    "various stakeholders", "ethical implications", "transformative paradigm shift",
    "responsible deployment", "in conclusion", "significant impact",
    "wide range of", "in the modern era", "increasingly important",
    "cutting-edge", "the fact that", "at the end of the day",
]

FORMULAIC_TRANSITIONS = [
    "furthermore", "moreover", "in addition", "therefore", "consequently",
    "overall", "additionally", "as a result", "in summary", "nevertheless",
]

SENSORY_WORDS = [
    "smell", "taste", "sound", "touch", "bright", "loud", "warm", "cold",
    "soft", "rough", "sweet", "bitter", "sour", "salty", "quiet", "sharp",
]

TIME_PLACE_MARKERS = [
    "yesterday", "today", "tomorrow", "last week", "this morning", "tonight",
    "downtown", "upstairs", "outside", "the porch", "the kitchen", "on the way",
]

ABSTRACT_NOUNS = [
    "society", "framework", "paradigm", "landscape", "ecosystem", "dynamic",
    "synergy", "strategy", "infrastructure", "methodology", "innovation",
]


def _count_phrases(text_lower, phrase_list):
    return sum(text_lower.count(p) for p in phrase_list)


def specificity_signal(text):
    """
    Specificity vs genericness. Returns {"score": float, "metrics": dict}.

    Higher score = more generic/formulaic = more AI-like.
    Lower score = more concrete/specific = more human-like.
    """

    text_lower = text.lower()
    words = re.findall(r"\b[\w']+\b", text_lower)
    word_count = len(words) or 1

    generic_phrase_count = _count_phrases(text_lower, GENERIC_PHRASES)
    formulaic_transition_count = _count_phrases(text_lower, FORMULAIC_TRANSITIONS)
    sensory_word_count = sum(1 for w in words if w in SENSORY_WORDS)
    time_or_place_marker_count = _count_phrases(text_lower, TIME_PLACE_MARKERS)
    abstract_noun_count = sum(1 for w in words if w in ABSTRACT_NOUNS)
    first_person_count = len(re.findall(r"\b(i|me|my|mine|we|us|our|ours)\b", text_lower))

    # crude proxy for named entities: capitalized words not at sentence start
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    named_entity_proxy_count = 0
    for sentence in sentences:
        tokens = sentence.split()
        for i, token in enumerate(tokens):
            clean = token.strip(",;:")
            if i > 0 and clean[:1].isupper() and clean.lower() not in ("i",):
                named_entity_proxy_count += 1

    concrete_detail_count = (
        sensory_word_count + time_or_place_marker_count + named_entity_proxy_count
    )

    generic_density = (generic_phrase_count + formulaic_transition_count + abstract_noun_count) / max(word_count / 40, 1)
    concrete_density = (concrete_detail_count + first_person_count) / max(word_count / 40, 1)

    generic_score = min(generic_density / 3, 1.0)
    concrete_score = min(concrete_density / 3, 1.0)

    # score leans AI-like (high) when generic evidence dominates concrete evidence
    score = 0.5 + (generic_score - concrete_score) / 2
    score = max(0.0, min(1.0, score))

    return {
        "score": round(score, 4),
        "metrics": {
            "concrete_detail_count": concrete_detail_count,
            "sensory_word_count": sensory_word_count,
            "first_person_count": first_person_count,
            "named_entity_proxy_count": named_entity_proxy_count,
            "time_or_place_marker_count": time_or_place_marker_count,
            "generic_phrase_count": generic_phrase_count,
            "abstract_noun_count": abstract_noun_count,
            "formulaic_transition_count": formulaic_transition_count,
        },
    }


# ---------------------------------------------------------------------------
# Score combination
# ---------------------------------------------------------------------------

def combine_scores(llm_score, stylometry_score, specificity_score):
    """
    Combines three signals into ai_likelihood, signal_agreement, and confidence.

    ai_likelihood: weighted average (LLM 50%, stylometry 30%, specificity 20%)
    signal_agreement: 1 - (max signal - min signal); high = signals agree
    confidence: blends distance-from-uncertain-middle with signal_agreement
    """

    ai_likelihood = round(
        (0.50 * llm_score) + (0.30 * stylometry_score) + (0.20 * specificity_score),
        4,
    )

    scores = [llm_score, stylometry_score, specificity_score]
    signal_spread = max(scores) - min(scores)
    signal_agreement = round(1 - signal_spread, 4)

    distance_from_middle = abs(ai_likelihood - 0.5) * 2
    confidence = round((0.65 * distance_from_middle) + (0.35 * signal_agreement), 4)

    return ai_likelihood, signal_agreement, confidence


def map_attribution(ai_likelihood, confidence):
    """
    Conservative attribution mapping. A high-confidence AI label requires
    BOTH high ai_likelihood AND high confidence, so signal disagreement
    (low confidence) can hold back what would otherwise be a likely_ai call.
    """

    if ai_likelihood >= 0.75 and confidence >= 0.65:
        return "likely_ai"

    if ai_likelihood <= 0.30 and confidence >= 0.65:
        return "likely_human"

    return "uncertain"