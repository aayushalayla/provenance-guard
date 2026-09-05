import detector


def test_word_tokenizer_handles_contractions_and_case():
    assert detector._words("Don't Stop") == ["don't", "stop"]


def test_sentence_splitter_preserves_case_for_entity_detection():
    assert detector._sentences("I met Ana. She left.") == ["I met Ana", "She left"]


def test_first_person_is_not_scored_by_stylometry():
    """first_person must not drive low_informality_score. A tiny residual
    difference is expected: pronouns are words, so they shift type_token_ratio."""
    plain = "The window was open. The room was cold. Nobody closed it."
    first_person = "My window was open. My room was cold. I never closed it."
    delta = abs(
        detector.stylometry_signal(plain)["score"]
        - detector.stylometry_signal(first_person)["score"]
    )
    assert delta < 0.02, f"stylometry moved {delta:.4f} on first-person alone"


def test_all_caps_is_not_double_counted_as_a_named_entity():
    result = detector.specificity_signal("they put WAY too much sodium in the broth")
    assert result["metrics"]["named_entity_proxy_count"] == 0


def test_no_confident_label_is_possible_when_the_llm_signal_is_down():
    """A neutral 0.5 placeholder must not be able to produce a label."""
    for sty in (0.0, 0.25, 0.5, 0.75, 1.0):
        for spec in (0.0, 0.25, 0.5, 0.75, 1.0):
            likelihood, _, confidence = detector.combine_scores(0.5, sty, spec)
            assert detector.map_attribution(likelihood, confidence) == "uncertain"


def test_high_ai_likelihood_never_returns_a_human_label():
    """Regression guard for the AI_LIKELY/HUMAN_LIKELY threshold swap."""
    for likelihood in (0.60, 0.70, 0.74, 0.749, 0.80, 0.95):
        for confidence in (0.60, 0.70, 0.90, 1.00):
            assert detector.map_attribution(likelihood, confidence) != "likely_human"


def test_contractions_are_detected():
    """Regression guard for the CONTRACTION_PATTERN quantifier."""
    metrics = detector.stylometry_signal(
        "i don't think we're going back, and they'll agree with me on that one"
    )["metrics"]
    assert metrics["contraction_count"] == 3


def test_short_text_confidence_is_capped():
    _, _, long_conf = detector.combine_scores(0.10, 0.15, 0.12, word_count=400)
    _, _, short_conf = detector.combine_scores(0.10, 0.15, 0.12, word_count=12)
    assert short_conf <= detector.SHORT_TEXT_CONFIDENCE_MAX < long_conf


def test_disagreement_blocks_a_likely_ai_label():
    likelihood, _, confidence = detector.combine_scores(0.95, 0.75, 0.30)
    assert likelihood >= 0.75
    assert detector.map_attribution(likelihood, confidence) == "uncertain"


def test_all_caps_is_reported_but_not_scored():
    plain = "they put way too much sodium in it and i was thirsty for hours"
    shouted = "they put WAY too much sodium in it and i was thirsty for hours"
    plain_r = detector.stylometry_signal(plain)
    shouted_r = detector.stylometry_signal(shouted)
    assert shouted_r["metrics"]["all_caps_count"] == 1
    assert plain_r["score"] == shouted_r["score"]


def test_agreement_counts_direction_not_magnitude():
    """Signals that agree on direction but differ in strength are in agreement."""
    _, agreement, _ = detector.combine_scores(0.82, 0.55, 0.91)
    assert agreement == 1.0
    _, agreement, _ = detector.combine_scores(0.22, 0.74, 0.50)
    assert agreement == round(1 / 3, 4)


def test_neutral_signal_does_not_count_as_agreement():
    """A 0.5 placeholder must not side with the ensemble."""
    _, with_neutral, _ = detector.combine_scores(0.5, 0.9, 0.9)
    _, all_agreeing, _ = detector.combine_scores(0.9, 0.9, 0.9)
    assert with_neutral == round(2 / 3, 4)
    assert all_agreeing == 1.0


def test_human_threshold_is_reachable():
    """The documented threshold must be attainable at full agreement."""
    likelihood, _, confidence = detector.combine_scores(0.10, 0.20, 0.15)
    assert likelihood <= detector.HUMAN_LIKELY_THRESHOLD
    assert detector.map_attribution(likelihood, confidence) == "likely_human"
