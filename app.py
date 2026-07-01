"""
app.py

Flask routes for Provenance Guard. Wires together detector.py (signals +
scoring), labels.py (transparency label text), storage.py (SQLite
persistence + audit log), and analytics.py (dashboard metrics).
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import analytics
import detector
import labels
import storage

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

storage.init_db()


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

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


def validate_appeal_payload(payload):
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object."

    content_id = payload.get("content_id")
    creator_id = payload.get("creator_id")
    creator_reasoning = payload.get("creator_reasoning")

    if not isinstance(content_id, str) or not content_id.strip():
        return False, "Missing or invalid 'content_id'."

    if not isinstance(creator_id, str) or not creator_id.strip():
        return False, "Missing or invalid 'creator_id'."

    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return False, "Missing or invalid 'creator_reasoning'."

    return True, None


def validate_certificate_payload(payload):
    if not isinstance(payload, dict):
        return False, "Request body must be a JSON object."

    content_id = payload.get("content_id")
    creator_id = payload.get("creator_id")

    if not isinstance(content_id, str) or not content_id.strip():
        return False, "Missing or invalid 'content_id'."

    if not isinstance(creator_id, str) or not creator_id.strip():
        return False, "Missing or invalid 'creator_id'."

    return True, None


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(429)
def too_many_requests(error):
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"service": "Provenance Guard", "status": "running", "version": "1.0"})


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    payload = request.get_json(silent=True)

    is_valid, error_message = validate_submit_payload(payload)
    if not is_valid:
        return jsonify({"error": error_message}), 400

    text = payload["text"].strip()
    creator_id = payload["creator_id"].strip()
    content_type = payload.get("content_type")

    content_id = new_id()

    llm_result = detector.llm_signal(text)
    stylometry_result = detector.stylometry_signal(text)
    specificity_result = detector.specificity_signal(text)

    ai_likelihood, signal_agreement, confidence = detector.combine_scores(
        llm_result["score"], stylometry_result["score"], specificity_result["score"]
    )

    attribution = detector.map_attribution(ai_likelihood, confidence)
    label = labels.label_for_attribution(attribution)

    created_at = utc_timestamp()

    record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "text_preview": text[:200],
        "content_type": content_type,
        "attribution": attribution,
        "ai_likelihood": ai_likelihood,
        "confidence": confidence,
        "signal_agreement": signal_agreement,
        "llm_score": llm_result["score"],
        "llm_reason": llm_result["reason"],
        "stylometry_score": stylometry_result["score"],
        "stylometry_metrics": stylometry_result["metrics"],
        "specificity_score": specificity_result["score"],
        "specificity_metrics": specificity_result["metrics"],
        "label": label,
        "status": "classified",
        "created_at": created_at,
    }

    storage.insert_classification(record)

    storage.write_audit_event(
        event_type="classification_created",
        content_id=content_id,
        creator_id=creator_id,
        payload={
            "attribution": attribution,
            "ai_likelihood": ai_likelihood,
            "confidence": confidence,
            "signal_agreement": signal_agreement,
            "llm_score": llm_result["score"],
            "stylometry_score": stylometry_result["score"],
            "specificity_score": specificity_result["score"],
            "status": "classified",
        },
    )

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "ai_likelihood": ai_likelihood,
        "confidence": confidence,
        "signal_agreement": signal_agreement,
        "label": label,
        "signals": {
            "llm": {"score": llm_result["score"], "reason": llm_result["reason"]},
            "stylometry": {"score": stylometry_result["score"], "metrics": stylometry_result["metrics"]},
            "specificity": {"score": specificity_result["score"], "metrics": specificity_result["metrics"]},
        },
        "status": "classified",
    }

    return jsonify(response_body), 201


@app.route("/appeal", methods=["POST"])
def appeal():
    payload = request.get_json(silent=True)

    is_valid, error_message = validate_appeal_payload(payload)
    if not is_valid:
        return jsonify({"error": error_message}), 400

    content_id = payload["content_id"].strip()
    creator_id = payload["creator_id"].strip()
    creator_reasoning = payload["creator_reasoning"].strip()
    optional_process_note = payload.get("optional_process_note")

    original = storage.get_classification(content_id)
    if original is None:
        return jsonify({"error": "No classification found for this content_id."}), 404
    
    if original["creator_id"] != creator_id:
    
        return (
        jsonify(
            {
                "error": "creator_id does not match the creator_id for this content_id."
            }
        ),
        400,
    )
    storage.update_classification_status(content_id, "under_review")

    appeal_id = new_id()
    created_at = utc_timestamp()

    storage.insert_appeal(
        {
            "appeal_id": appeal_id,
            "content_id": content_id,
            "creator_id": creator_id,
            "creator_reasoning": creator_reasoning,
            "optional_process_note": optional_process_note,
            "status": "under_review",
            "created_at": created_at,
        }
    )

    storage.write_audit_event(
        event_type="appeal_submitted",
        content_id=content_id,
        creator_id=creator_id,
        payload={
            "appeal_id": appeal_id,
            "original_attribution": original["attribution"],
            "original_ai_likelihood": original["ai_likelihood"],
            "original_confidence": original["confidence"],
            "creator_reasoning": creator_reasoning,
            "optional_process_note": optional_process_note,
            "status": "under_review",
        },
    )

    return (
        jsonify(
            {
                "appeal_id": appeal_id,
                "content_id": content_id,
                "status": "under_review",
                "message": "Appeal received. This content has been marked for human review.",
            }
        ),
        201,
    )


@app.route("/appeals", methods=["GET"])
def get_appeals():
    return jsonify({"appeals": storage.all_appeals()}), 200


@app.route("/log", methods=["GET"])
def get_log():
    return jsonify({"entries": storage.read_audit_events()}), 200


@app.route("/analytics", methods=["GET"])
def get_analytics():
    return jsonify(analytics.compute_analytics()), 200


@app.route("/certificate", methods=["POST"])
def certificate():
    payload = request.get_json(silent=True)

    is_valid, error_message = validate_certificate_payload(payload)
    if not is_valid:
        return jsonify({"error": error_message}), 400

    content_id = payload["content_id"].strip()
    creator_id = payload["creator_id"].strip()
    verification_note = payload.get("verification_note")

    original = storage.get_classification(content_id)
    if original is None:
        return jsonify({"error": "No classification found for this content_id."}), 404

    certificate_id = new_id()
    certificate_label = "Creator-attested human process"
    display_text = (
        "The creator has submitted additional process context for this work. "
        "This certificate records a human authorship claim but does not "
        "independently prove authorship."
    )
    created_at = utc_timestamp()

    storage.insert_certificate(
        {
            "certificate_id": certificate_id,
            "content_id": content_id,
            "creator_id": creator_id,
            "certificate_label": certificate_label,
            "display_text": display_text,
            "verification_note": verification_note,
            "created_at": created_at,
        }
    )

    storage.write_audit_event(
        event_type="certificate_created",
        content_id=content_id,
        creator_id=creator_id,
        payload={
            "certificate_id": certificate_id,
            "certificate_label": certificate_label,
        },
    )

    return (
        jsonify(
            {
                "certificate_id": certificate_id,
                "content_id": content_id,
                "certificate_label": certificate_label,
                "display_text": display_text,
            }
        ),
        201,
    )


if __name__ == "__main__":
    app.run(debug=False, port=5001)