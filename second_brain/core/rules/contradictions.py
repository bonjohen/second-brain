"""Contradiction detection heuristics for beliefs."""

from __future__ import annotations

import uuid

from second_brain.core.models import BeliefStatus
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService

# Word pairs that indicate opposing predicates
OPPOSING_PAIRS: list[tuple[str, str]] = [
    ("fast", "slow"),
    ("good", "bad"),
    ("easy", "hard"),
    ("simple", "complex"),
    ("safe", "unsafe"),
    ("efficient", "inefficient"),
    ("reliable", "unreliable"),
    ("secure", "insecure"),
    ("stable", "unstable"),
    ("useful", "useless"),
    ("true", "false"),
    ("correct", "incorrect"),
    ("possible", "impossible"),
    ("always", "never"),
    ("increase", "decrease"),
    ("better", "worse"),
]


def detect_contradictions(
    belief_id: uuid.UUID,
    belief_service: BeliefService,
    edge_service: EdgeService,
) -> list[uuid.UUID]:
    """Detect beliefs that may contradict the given belief.

    Returns a list of belief IDs that are potential contradictions.

    Heuristics:
    1. Exact negation: claim contains "not" version of another claim (or vice versa)
    2. Same-subject opposing predicates: claims share subject words but use opposing words
    """
    belief = belief_service.get_belief(belief_id)
    if belief is None:
        return []

    claim_words = set(belief.claim_text.lower().split())
    claim_lower = belief.claim_text.lower().strip()

    # Get all active/proposed beliefs to check against
    candidates: list = []
    for status in (BeliefStatus.PROPOSED, BeliefStatus.ACTIVE):
        candidates.extend(belief_service.list_beliefs(status_filter=status, limit=1000))

    contradictions: list[uuid.UUID] = []

    for other in candidates:
        if other.belief_id == belief_id:
            continue

        other_lower = other.claim_text.lower().strip()
        other_words = set(other_lower.split())

        # Heuristic 1: exact negation detection
        # Check if one claim is "not" version of another
        if _is_negation(claim_lower, other_lower):
            contradictions.append(other.belief_id)
            continue

        # Heuristic 2: same-subject opposing predicates
        # Claims must share at least 2 meaningful words (subject overlap)
        shared = claim_words & other_words
        # Filter out very common words
        stop_words = {"is", "a", "the", "an", "and", "or", "of", "in", "to", "for", "it", "are"}
        meaningful_shared = shared - stop_words
        if len(meaningful_shared) >= 2 and _has_opposing_words(claim_words, other_words):
            contradictions.append(other.belief_id)

    return contradictions


def _is_negation(claim_a: str, claim_b: str) -> bool:
    """Check if one claim is a negation of the other."""
    # "X is Y" vs "X is not Y"
    if claim_a.replace(" not ", " ") == claim_b:
        return True
    if claim_b.replace(" not ", " ") == claim_a:
        return True

    # "X is Y" vs "X isn't Y"
    return claim_a.replace("n't ", " ") == claim_b.replace(" not ", " ")


def _has_opposing_words(words_a: set[str], words_b: set[str]) -> bool:
    """Check if the two word sets contain opposing word pairs."""
    for word_1, word_2 in OPPOSING_PAIRS:
        if (word_1 in words_a and word_2 in words_b) or (
            word_2 in words_a and word_1 in words_b
        ):
            return True
    return False
