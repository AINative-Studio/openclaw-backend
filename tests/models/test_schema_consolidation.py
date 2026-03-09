"""
Test Schema Consolidation

Verifies that TaskLease model is consolidated into single canonical schema.
Tests MUST fail initially (RED state) before implementation.

Issue #116: Consolidate PostgreSQL Schema Models
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


class TestSchemaConsolidation:
    """Test suite for schema consolidation"""

    def test_prevents_import_from_task_models(self):
        """Test that task_models.py TaskLease is deprecated"""
        # This should fail initially - deprecated model still exists
        with pytest.raises(ImportError):
            from backend.models.task_models import TaskLease

    def test_prevents_import_from_task_lease_models(self):
        """Test that task_lease_models.py TaskLease is deprecated"""
        # This should fail initially - deprecated model still exists
        with pytest.raises(ImportError):
            from backend.models.task_lease_models import TaskLease

    def test_allows_import_from_canonical_location(self):
        """Test that canonical TaskLease can be imported"""
        # This should fail initially - canonical model doesn't exist yet
        from backend.models.task_lease import TaskLease
        assert TaskLease is not None
        assert TaskLease.__tablename__ == "task_leases"


class TestPostgreSQLSchemaColumns:
    """Verify TaskLease has correct PostgreSQL columns"""

    def test_has_peer_id_column(self, db_session: Session):
        """Test that TaskLease has peer_id (NOT owner_peer_id)"""
        # This should fail initially - wrong column name may exist
        from backend.models.task_lease import TaskLease

        inspector = inspect(db_session.bind)
        columns = {col['name'] for col in inspector.get_columns('task_leases')}

        assert 'peer_id' in columns
        assert 'owner_peer_id' not in columns

    def test_has_uuid_primary_key(self, db_session: Session):
        """Test that TaskLease uses UUID primary key"""
        from backend.models.task_lease import TaskLease

        inspector = inspect(db_session.bind)
        pk_constraint = inspector.get_pk_constraint('task_leases')
        pk_columns = pk_constraint['constrained_columns']

        assert len(pk_columns) == 1
        assert pk_columns[0] == 'id'

        # Verify it's UUID type
        columns = {col['name']: col for col in inspector.get_columns('task_leases')}
        assert 'UUID' in str(columns['id']['type'])

    def test_has_required_columns(self, db_session: Session):
        """Test that all required columns exist"""
        from backend.models.task_lease import TaskLease

        inspector = inspect(db_session.bind)
        columns = {col['name'] for col in inspector.get_columns('task_leases')}

        required_columns = {
            'id',
            'task_id',
            'peer_id',
            'lease_token',
            'expires_at',
            'created_at'
        }

        assert required_columns.issubset(columns)


class TestTaskStatusEnum:
    """Verify TaskStatus enum has 7 states"""

    def test_has_seven_status_values(self):
        """Test that TaskStatus has all 7 states"""
        from backend.models.task_lease import TaskStatus

        expected_states = {
            "QUEUED",
            "LEASED",
            "RUNNING",
            "COMPLETED",
            "FAILED",
            "EXPIRED",
            "PERMANENTLY_FAILED"
        }

        actual_states = {status.name for status in TaskStatus}
        assert actual_states == expected_states


class TestAllServicesUseCanonicalModel:
    """Verify all services import from canonical location"""

    def test_verifies_no_deprecated_imports(self):
        """Test that no service imports from deprecated locations"""
        import os
        import ast

        services_dir = "backend/services"
        deprecated_imports = [
            "from backend.models.task_models import",
            "from backend.models.task_queue import TaskLease",
            "from backend.models.task_lease_models import"
        ]

        canonical_import = "from backend.models.task_lease import"

        violations = []

        for filename in os.listdir(services_dir):
            if not filename.endswith('.py'):
                continue

            filepath = os.path.join(services_dir, filename)
            with open(filepath) as f:
                content = f.read()

            # Check for deprecated imports
            for deprecated in deprecated_imports:
                if deprecated in content and "TaskLease" in content:
                    violations.append(f"{filename} uses deprecated import")

        # This should fail initially - services still use old imports
        assert len(violations) == 0, f"Found deprecated imports: {violations}"


class TestTaskLeaseModel:
    """Test TaskLease model functionality"""

    def test_creates_task_lease_with_peer_id(self, db_session: Session):
        """Test creating TaskLease with peer_id field"""
        from backend.models.task_lease import TaskLease, Task, TaskStatus
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        # Create a task first
        task = Task(
            task_type="test",
            payload={"test": "data"},
            status=TaskStatus.QUEUED
        )
        db_session.add(task)
        db_session.flush()

        # Create lease with peer_id using unique token
        unique_token = f"test-token-{uuid4()}"
        lease = TaskLease(
            task_id=task.id,
            peer_id="12D3KooWTest123",
            lease_token=unique_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            lease_duration_seconds=3600
        )
        db_session.add(lease)
        db_session.commit()

        # Verify
        assert lease.peer_id == "12D3KooWTest123"
        assert lease.task_id == task.id

    def test_queries_by_peer_id(self, db_session: Session):
        """Test querying TaskLease by peer_id"""
        from backend.models.task_lease import TaskLease

        # This should fail initially if using wrong column
        result = db_session.query(TaskLease).filter(
            TaskLease.peer_id == "test-peer"
        ).first()

        # Should not raise AttributeError for peer_id
        assert True  # If we get here, peer_id exists
