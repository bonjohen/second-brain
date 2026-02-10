"""Contradiction detection heuristics for beliefs."""

from __future__ import annotations

import logging
import uuid

from second_brain.core.constants import DEFAULT_BATCH_SIZE, STOP_WORDS
from second_brain.core.models import Belief, BeliefStatus
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService

logger = logging.getLogger(__name__)

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


DEFAULT_MAX_CANDIDATES = 500


def load_candidate_beliefs(
    belief_service: BeliefService,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[Belief]:
    """Pre-load proposed and active beliefs for contradiction checking.

    Callers processing multiple beliefs should call this once and pass the
    result to ``detect_contradictions`` to avoid redundant O(n) fetches.
    """
    candidates: list[Belief] = []
    for status in (BeliefStatus.PROPOSED, BeliefStatus.ACTIVE):
        offset = 0
        batch_size = DEFAULT_BATCH_SIZE
        while True:
            batch = belief_service.list_beliefs(
                status_filter=status, limit=batch_size, offset=offset
            )
            if not batch:
                break
            candidates.extend(batch)
            if len(candidates) >= max_candidates:
                candidates = candidates[:max_candidates]
                break
            offset += batch_size
        if len(candidates) >= max_candidates:
            break

    if len(candidates) >= max_candidates:
        logger.warning(
            "Contradiction candidates capped at %d; some beliefs may be skipped",
            max_candidates,
        )
    return candidates


def detect_contradictions(
    belief_id: uuid.UUID,
    belief_service: BeliefService,
    edge_service: EdgeService,
    *,
    candidates: list[Belief] | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[uuid.UUID]:
    """Detect beliefs that may contradict the given belief.

    Returns a list of belief IDs that are potential contradictions.

    Pass pre-loaded *candidates* to avoid re-fetching all beliefs on every
    call (important when checking contradictions in a loop).

    Heuristics:
    1. Exact negation: claim contains "not" version of another claim (or vice versa)
    2. Same-subject opposing predicates: claims share subject words but use opposing words
    """
    belief = belief_service.get_belief(belief_id)
    if belief is None:
        return []

    claim_words = set(belief.claim_text.lower().split())
    claim_lower = belief.claim_text.lower().strip()

    # Use pre-loaded candidates or fetch them
    if candidates is None:
        candidates = load_candidate_beliefs(belief_service, max_candidates)

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
        meaningful_shared = shared - STOP_WORDS
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
