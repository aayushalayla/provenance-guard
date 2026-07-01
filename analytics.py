"""
analytics.py

Aggregate metrics over stored classifications and appeals, for the
stretch-feature GET /analytics endpoint.
"""

import storage


def compute_analytics():
    classifications = storage.all_classifications()
    appeals = storage.all_appeals()

    total_submissions = len(classifications)

    likely_ai_count = sum(1 for c in classifications if c["attribution"] == "likely_ai")
    likely_human_count = sum(1 for c in classifications if c["attribution"] == "likely_human")
    uncertain_count = sum(1 for c in classifications if c["attribution"] == "uncertain")

    appeal_count = len(appeals)
    appeal_rate = round(appeal_count / total_submissions, 4) if total_submissions else 0.0

    if total_submissions:
        average_ai_likelihood = round(
            sum(c["ai_likelihood"] for c in classifications) / total_submissions, 4
        )
        average_confidence = round(
            sum(c["confidence"] for c in classifications) / total_submissions, 4
        )
    else:
        average_ai_likelihood = 0.0
        average_confidence = 0.0

    counts = {
        "likely_ai": likely_ai_count,
        "likely_human": likely_human_count,
        "uncertain": uncertain_count,
    }
    most_common_attribution = max(counts, key=counts.get) if total_submissions else None

    return {
        "total_submissions": total_submissions,
        "likely_ai_count": likely_ai_count,
        "likely_human_count": likely_human_count,
        "uncertain_count": uncertain_count,
        "appeal_count": appeal_count,
        "appeal_rate": appeal_rate,
        "average_ai_likelihood": average_ai_likelihood,
        "average_confidence": average_confidence,
        "most_common_attribution": most_common_attribution,
        "false_positive_risk_note": (
            "High-confidence AI labels require both high AI-likelihood "
            "(>= 0.75) and high confidence (>= 0.65)."
        ),
    }