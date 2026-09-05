"""
analytics.py

Aggregate metrics over stored classifications and appeals,
for GET /analytics endpoint.
"""

from collections import Counter

import storage
from detector import AI_LIKELY_THRESHOLD, ATTRIBUTIONS, CONFIDENCE_THRESHOLD


def compute_analytics():
    classifications = storage.all_classifications()
    appeals = storage.all_appeals()

    total_submissions = len(classifications)

    counts = Counter(c["attribution"] for c in classifications)
    likely_ai_count = counts.get("likely_ai", 0)
    likely_human_count = counts.get("likely_human", 0)
    uncertain_count = counts.get("uncertain", 0)

    unrecognized = {k: v for k, v in counts.items() if k not in ATTRIBUTIONS}

    appeal_count = len(appeals)
    appealed_content_count = len({a["content_id"] for a in appeals})
    appeal_rate = (
        round(appealed_content_count / total_submissions, 4)
        if total_submissions
        else 0.0
    )

    if total_submissions:
        average_ai_likelihood = round(
            sum(c["ai_likelihood"] for c in classifications) / total_submissions, 4
        )
        average_confidence = round(
            sum(c["confidence"] for c in classifications) / total_submissions, 4
        )
        average_signal_agreement = round(
            sum(c["signal_agreement"] for c in classifications) / total_submissions, 4
        )
    else:
        average_ai_likelihood = 0.0
        average_confidence = 0.0
        average_signal_agreement = 0.0

    known = {a: counts.get(a, 0) for a in ATTRIBUTIONS}
    most_common_attribution = max(known, key=known.get) if total_submissions else None

    return {
        "total_submissions": total_submissions,
        "likely_ai_count": likely_ai_count,
        "likely_human_count": likely_human_count,
        "uncertain_count": uncertain_count,
        "unrecognized_attributions": unrecognized,
        "appealed_content_count": appealed_content_count,
        "appeal_count": appeal_count,
        "appeal_rate": appeal_rate,
        "average_ai_likelihood": average_ai_likelihood,
        "average_confidence": average_confidence,
        "average_signal_agreement": average_signal_agreement,
        "most_common_attribution": most_common_attribution,
        "false_positive_risk_note": (
            "A high-confidence AI label requires both high AI-likelihood "
            f"(>= {AI_LIKELY_THRESHOLD}) and high confidence "
            f"(>= {CONFIDENCE_THRESHOLD})."
        ),
    }
