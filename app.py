import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from groq import Groq


load_dotenv()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

AUDIT_LOG_PATH = Path("audit_log.jsonl")


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def validate_submit_payload(payload):
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object."

    text = payload.get("text")
    creator_id = payload.get("creator_id")

    if not isinstance(text, str) or not text.strip():
        return False, "Missing or invalid 'text'."

    if not isinstance(creator_id, str) or not creator_id.strip():
        return False, "Missing or invalid 'creator_id'."

    return True, None


def clamp_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5

    return max(0.0, min(1.0, score))


def groq_llm_signal(text):
    """
    First detection signal.

    Returns an AI-likeness score from 0.0 to 1.0.

    0.0 = strongly human-like
    0.5 = uncertain
    1.0 = strongly AI-like
    """

    if groq_client is None:
        return {
            "score": 0.5,
            "reason": "Groq signal unavailable because GROQ_API_KEY is not set. Using neutral placeholder score.",
        }

    system_prompt = """
You are an authorship-transparency classifier.

Your task is to evaluate whether a submitted text appears AI-generated or human-written based on writing style.

Do not classify based on topic alone. Formal subject matter is not enough to call something AI-generated.

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

AI-like signs:
- generic phrasing
- polished but bland structure
- formulaic transitions
- lack of personal detail
- balanced, corporate, or template-like prose
- cautious generalizations without friction or specificity

Human-like signs:
- concrete personal detail
- uneven rhythm
- idiosyncratic phrasing
- slang or informal turns
- small imperfections
- specific lived context
""".strip()

    user_prompt = f"""
Analyze this text for AI-likeness.

Text:
{text}
""".strip()

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )

        raw_content = response.choices[0].message.content.strip()
        parsed = json.loads(raw_content)

        return {
            "score": clamp_score(parsed.get("score")),
            "reason": str(parsed.get("reason", "No reason provided.")),
        }

    except Exception as error:
        return {
            "score": 0.5,
            "reason": f"Groq signal failed. Using neutral placeholder score. Error: {error}",
        }

def stylometry_signal(text):
    """
    Second detection signal.

    Returns a structural AI-likeness score from 0.0 to 1.0.

    0.0 = structurally human-like
    0.5 = mixed / unclear
    1.0 = structurally AI-like
    """

    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"\b[\w']+\b", text.lower())
    punctuation_marks = re.findall(r"[.,!?;:]", text)

    if not words:
        return {
            "score": 0.5,
            "metrics": {
                "word_count": 0,
                "sentence_count": 0,
                "average_sentence_length": 0,
                "sentence_length_variance": 0,
                "type_token_ratio": 0,
                "punctuation_density": 0,
                "contraction_count": 0,
                "first_person_count": 0,
                "slang_count": 0,
                "all_caps_count": 0,
            },
        }

    word_count = len(words)
    sentence_count = max(1, len(sentences))

    sentence_lengths = [
        len(re.findall(r"\b[\w']+\b", sentence.lower()))
        for sentence in sentences
    ]

    average_sentence_length = word_count / sentence_count

    if len(sentence_lengths) > 1:
        mean_length = sum(sentence_lengths) / len(sentence_lengths)
        sentence_length_variance = sum(
            (length - mean_length) ** 2 for length in sentence_lengths
        ) / len(sentence_lengths)
    else:
        sentence_length_variance = 0

    type_token_ratio = len(set(words)) / word_count
    punctuation_density = len(punctuation_marks) / max(1, len(text))

    contractions = re.findall(r"\b\w+'\w+\b", text.lower())
    first_person = re.findall(r"\b(i|me|my|mine|we|us|our|ours)\b", text.lower())
    slang = re.findall(
        r"\b(ok|yeah|lol|nah|gonna|wanna|kinda|sorta|honestly|bro|dude|mid)\b",
        text.lower(),
    )
    all_caps_words = re.findall(r"\b[A-Z]{2,}\b", text)

    uniformity_score = 1.0 - min(sentence_length_variance / 50, 1.0)
    long_sentence_score = min(average_sentence_length / 25, 1.0)
    low_informality_score = 1.0 - min(
        (len(contractions) + len(first_person) + len(slang) + len(all_caps_words)) / 6,
        1.0,
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
            "slang_count": len(slang),
            "all_caps_count": len(all_caps_words),
        },
    }

def combine_two_signal_scores(llm_score, stylometry_score):
    """
    M4 scoring.

    Combines the LLM signal and stylometric signal into one AI-likeness score.
    """

    combined_score = (0.65 * llm_score) + (0.35 * stylometry_score)
    return round(combined_score, 4)


def attribution_from_combined_score(ai_likelihood, confidence):
    if ai_likelihood >= 0.70:
        return "likely_ai"

    if ai_likelihood <= 0.34:
        return "likely_human"

    return "uncertain"

    return "uncertain"
def combine_two_signal_scores(llm_score, stylometry_score):
    """
    M4 scoring.

    Combines the LLM signal and stylometric signal into one AI-likeness score.
    """

    combined_score = (0.65 * llm_score) + (0.35 * stylometry_score)
    return round(combined_score, 4)


def attribution_from_combined_score(ai_likelihood, confidence):
    if ai_likelihood >= 0.70:
        return "likely_ai"

    if ai_likelihood <= 0.34:
        return "likely_human"

    return "uncertain"

def attribution_from_llm_score(llm_score):
    """
    Temporary M3 attribution mapping using only Signal 1.
    This will be replaced in M4 when the second signal is added.
    """

    if llm_score >= 0.75:
        return "likely_ai"

    if llm_score <= 0.30:
        return "likely_human"

    return "uncertain"


def placeholder_confidence(llm_score):
    """
    Temporary M3 confidence.

    In M4, confidence will combine LLM + stylometry.
    For now, confidence is based on distance from the uncertain middle.
    """

    distance_from_middle = abs(llm_score - 0.5) * 2
    return round(distance_from_middle, 4)

def placeholder_label(attribution):
    """
    Temporary label.

    In M5, this becomes the final transparency-label function.
    """

    if attribution == "likely_ai":
        return (
            "M4 placeholder: This work currently appears likely AI-generated "
            "based on the first two detection signals. Final transparency labels will be added later."
        )

    if attribution == "likely_human":
        return (
            "M4 placeholder: This work currently appears likely human-written "
            "based on the first two detection signals. Final transparency labels will be added later."
        )

    return (
        "M4 placeholder: This work could not be clearly classified "
        "based on the first two detection signals. Final transparency labels will be added later."
    )

def write_audit_entry(entry):
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(entry) + "\n")


def read_audit_log(limit=20):
    if not AUDIT_LOG_PATH.exists():
        return []

    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as log_file:
        lines = log_file.readlines()

    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return entries


@app.route("/", methods=["GET"])
def health_check():
    return jsonify(
        {
            "service": "Provenance Guard",
            "status": "running",
            "milestone": "M4",
        }
    )


@app.route("/submit", methods=["POST"])
@app.route("/submit", methods=["POST"])
def submit():
    payload = request.get_json(silent=True)

    is_valid, error_message = validate_submit_payload(payload)
    if not is_valid:
        return jsonify({"error": error_message}), 400

    text = payload["text"].strip()
    creator_id = payload["creator_id"].strip()

    content_id = str(uuid.uuid4())

    llm_signal = groq_llm_signal(text)
    llm_score = round(llm_signal["score"], 4)

    stylometry = stylometry_signal(text)
    stylometry_score = round(stylometry["score"], 4)

    combined_score = combine_two_signal_scores(llm_score, stylometry_score)

    ai_likelihood = combined_score
    confidence = round(abs(ai_likelihood - 0.5) * 2, 4)

    attribution = attribution_from_combined_score(ai_likelihood, confidence)
    label = placeholder_label(attribution)

    audit_entry = {
        "event_type": "classification_created",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": utc_timestamp(),
        "attribution": attribution,
        "confidence": confidence,
        "ai_likelihood": ai_likelihood,
        "combined_score": combined_score,
        "llm_score": llm_score,
        "llm_reason": llm_signal["reason"],
        "stylometry_score": stylometry_score,
        "stylometry_metrics": stylometry["metrics"],
        "label": label,
        "status": "classified",
        "milestone_note": "M4 uses Groq LLM signal plus stylometric heuristics.",
    }

    write_audit_entry(audit_entry)

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "ai_likelihood": ai_likelihood,
        "confidence": confidence,
        "combined_score": combined_score,
        "label": label,
        "signals": {
            "llm": {
                "score": llm_score,
                "reason": llm_signal["reason"],
            },
            "stylometry": {
                "score": stylometry_score,
                "metrics": stylometry["metrics"],
            },
        },
        "status": "classified",
    }

    return jsonify(response_body), 201


@app.route("/log", methods=["GET"])
def get_log():
    return jsonify({"entries": read_audit_log()}), 200



if __name__ == "__main__":
    app.run(debug=True, port=5000)