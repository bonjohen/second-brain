"""Contradiction detection — heuristic rules per design.md Section 5.3.

Rules:
  - Exact negation detection (claim vs "not claim")
  - Same-subject opposing predicates ("X is Y" vs "X is not Y")
"""

from __future__ import annotations

import re


# Negation patterns
_NEGATION_PREFIXES = [
    "not ", "no ", "never ", "cannot ", "isn't ", "aren't ", "doesn't ",
    "don't ", "won't ", "hasn't ", "haven't ", "wasn't ", "weren't ",
    "it is false that ", "it is not true that ", "it is not the case that ",
]

_IS_PATTERN = re.compile(r"^(.+?)\s+is\s+(.+)$", re.IGNORECASE)
_IS_NOT_PATTERN = re.compile(r"^(.+?)\s+is\s+not\s+(.+)$", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def is_exact_negation(claim_a: str, claim_b: str) -> bool:
    """Check if one claim is the exact negation of the other."""
    a = normalize(claim_a)
    b = normalize(claim_b)

    for prefix in _NEGATION_PREFIXES:
        # "X" vs "not X"
        if a == prefix + b or b == prefix + a:
            return True
        # Strip prefix from one and compare
        if a.startswith(prefix) and a[len(prefix):] == b:
            return True
        if b.startswith(prefix) and b[len(prefix):] == a:
            return True

    return False


def is_opposing_predicate(claim_a: str, claim_b: str) -> bool:
    """Check if claims have same subject but opposing predicates.

    e.g. "Python is fast" vs "Python is not fast"
    """
    a = normalize(claim_a)
    b = normalize(claim_b)

    # Check "X is Y" vs "X is not Y"
    match_a_pos = _IS_PATTERN.match(a)
    match_b_neg = _IS_NOT_PATTERN.match(b)
    if match_a_pos and match_b_neg:
        if match_a_pos.group(1) == match_b_neg.group(1) and match_a_pos.group(2) == match_b_neg.group(2):
            return True

    match_a_neg = _IS_NOT_PATTERN.match(a)
    match_b_pos = _IS_PATTERN.match(b)
    if match_a_neg and match_b_pos:
        if match_a_neg.group(1) == match_b_pos.group(1) and match_a_neg.group(2) == match_b_pos.group(2):
            return True

    return False


def detect_contradiction(claim_a: str, claim_b: str) -> bool:
    """Returns True if the two claims contradict each other."""
    return is_exact_negation(claim_a, claim_b) or is_opposing_predicate(claim_a, claim_b)
