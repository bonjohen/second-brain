"""Shared constants — single source of truth for values used across modules."""

# Batch processing
DEFAULT_BATCH_SIZE = 500

# Confidence
DEFAULT_BASE_CONFIDENCE = 0.5
CONFIDENCE_STEP = 0.1
LOW_CONFIDENCE_THRESHOLD = 0.3

# Snippet lengths (CLI display)
SNIPPET_SHORT = 120
SNIPPET_MEDIUM = 200
SNIPPET_FIRST_LINE = 100

# Report
REPORT_QUERY_LIMIT = 100_000

# NLP
STOP_WORDS: frozenset[str] = frozenset(
    {"is", "a", "the", "an", "and", "or", "of", "in", "to", "for", "it", "are"}
)

# Dispatcher
MAX_SIGNAL_RETRIES = 5

# Signals
DEFAULT_UNPROCESSED_LIMIT = 1000
