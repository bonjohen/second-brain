"""Reports — health/status report generation.

Per design.md Section 7.3: Generate report artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from second_brain.core.models import BeliefStatus
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database


@dataclass
class HealthReport:
    generated_at: str
    note_count: int = 0
    source_count: int = 0
    belief_counts: dict[str, int] = field(default_factory=dict)
    edge_count: int = 0
    pending_signal_count: int = 0
    audit_entry_count: int = 0
    contradiction_count: int = 0
    stale_beliefs: list[str] = field(default_factory=list)

    @property
    def total_beliefs(self) -> int:
        return sum(self.belief_counts.values())


class ReportService:
    def __init__(self, db: Database):
        self.db = db

    def generate_health_report(self) -> HealthReport:
        """Generate a full health/status report."""
        report = HealthReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Counts
        row = self.db.fetchone("SELECT COUNT(*) as cnt FROM notes")
        report.note_count = row["cnt"] if row else 0

        row = self.db.fetchone("SELECT COUNT(*) as cnt FROM sources")
        report.source_count = row["cnt"] if row else 0

        row = self.db.fetchone("SELECT COUNT(*) as cnt FROM edges")
        report.edge_count = row["cnt"] if row else 0

        row = self.db.fetchone("SELECT COUNT(*) as cnt FROM audit_log")
        report.audit_entry_count = row["cnt"] if row else 0

        # Belief counts by status
        for status in BeliefStatus:
            row = self.db.fetchone(
                "SELECT COUNT(*) as cnt FROM beliefs WHERE status = ?",
                (status.value,),
            )
            report.belief_counts[status.value] = row["cnt"] if row else 0

        # Pending signals
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM signals WHERE processed_at IS NULL"
        )
        report.pending_signal_count = row["cnt"] if row else 0

        # Contradiction edges
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM edges WHERE rel_type = 'contradicts'"
        )
        report.contradiction_count = row["cnt"] if row else 0

        return report
