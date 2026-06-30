import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

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
    Temporary M3 label.

    In M5, this becomes the final transparency-label function.
    """

    if attribution == "likely_ai":
        return "M3 placeholder: This work currently appears likely AI-generated based on the first detection signal based on the first detection signal. Final transparency labels will be added later."

    if attribution == "likely_human":
        return "M3 placeholder: This work currently appears likely human-written based on the first detection signal based on the first detection signal. Final transparency labels will be added later."

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
            "milestone": "M3",
        }
    )


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

    attribution = attribution_from_llm_score(llm_score)
    confidence = placeholder_confidence(llm_score)
    label = placeholder_label(attribution)

    audit_entry = {
        "event_type": "classification_created",
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": utc_timestamp(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "llm_reason": llm_signal["reason"],
        "label": label,
        "status": "classified",
        "milestone_note": "M3 uses only the Groq LLM signal. M4 will add stylometric heuristics.",
    }

    write_audit_entry(audit_entry)

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm": {
                "score": llm_score,
                "reason": llm_signal["reason"],
            }
        },
        "status": "classified",
    }

    return jsonify(response_body), 201


@app.route("/log", methods=["GET"])
def get_log():
    return jsonify({"entries": read_audit_log()}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)