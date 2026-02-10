"""Shared test fixtures."""

import pytest

from second_brain.core.services.audit import AuditService
from second_brain.core.services.beliefs import BeliefService
from second_brain.core.services.edges import EdgeService
from second_brain.core.services.notes import NoteService
from second_brain.core.services.signals import SignalService
from second_brain.storage.sqlite import Database


@pytest.fixture
def db(tmp_path):
    """Create a fresh database on disk (needed for FTS5 trigger support)."""
    db_path = tmp_path / "test_brain.db"
    database = Database(db_path)
    yield database
    database.close()


@pytest.fixture
def audit_service(db):
    return AuditService(db)


@pytest.fixture
def signal_service(db):
    return SignalService(db)


@pytest.fixture
def note_service(db, audit_service):
    return NoteService(db, audit_service)


@pytest.fixture
def edge_service(db):
    return EdgeService(db)


@pytest.fixture
def belief_service(db, audit_service, edge_service):
    return BeliefService(db, audit_service, edge_service)
