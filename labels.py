"""
labels.py

Maps an attribution category to the exact reader-facing transparency
label text.
"""

LABELS = {
    "likely_ai": (
        "This work shows strong signs of AI-generated text based on an automated "
        "multi-signal review. This label is not a final judgment of authorship "
        "and may be appealed by the creator."
    ),
    "likely_human": (
        "This work shows strong signs of human authorship based on an automated "
        "multi-signal review. This label is not a guarantee, but the available "
        "signals support human authorship."
    ),
    "uncertain": (
        "This work could not be classified with high confidence. The system found "
        "mixed or limited evidence, so readers should treat authorship as unresolved "
        "unless more context is provided."
    ),
}


def label_for_attribution(attribution):
    return LABELS.get(attribution, LABELS["uncertain"])
