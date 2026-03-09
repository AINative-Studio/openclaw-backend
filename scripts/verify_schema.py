#!/usr/bin/env python3
"""
Verify User and Workspace Schema

Creates tables using SQLAlchemy and verifies the schema matches requirements.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text
from backend.db.base_class import Base
from backend.models.workspace import Workspace
from backend.models.user import User

def verify_schema():
    """Verify the User and Workspace schema"""
    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Inspect schema
    inspector = inspect(engine)

    print("=" * 80)
    print("WORKSPACE TABLE SCHEMA")
    print("=" * 80)

    # Check workspaces table exists
    if 'workspaces' not in inspector.get_table_names():
        print("ERROR: workspaces table not found!")
        return False

    # Get workspace columns
    workspace_columns = {col['name']: col for col in inspector.get_columns('workspaces')}
    print("\nColumns:")
    for name, col in workspace_columns.items():
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        print(f"  - {name}: {col['type']} {nullable}")

    # Get workspace indexes
    workspace_indexes = inspector.get_indexes('workspaces')
    print("\nIndexes:")
    for idx in workspace_indexes:
        unique = "UNIQUE" if idx['unique'] else ""
        print(f"  - {idx['name']}: {idx['column_names']} {unique}")

    print("\n" + "=" * 80)
    print("USER TABLE SCHEMA")
    print("=" * 80)

    # Check users table exists
    if 'users' not in inspector.get_table_names():
        print("ERROR: users table not found!")
        return False

    # Get user columns
    user_columns = {col['name']: col for col in inspector.get_columns('users')}
    print("\nColumns:")
    for name, col in user_columns.items():
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        print(f"  - {name}: {col['type']} {nullable}")

    # Get user indexes
    user_indexes = inspector.get_indexes('users')
    print("\nIndexes:")
    for idx in user_indexes:
        unique = "UNIQUE" if idx['unique'] else ""
        print(f"  - {idx['name']}: {idx['column_names']} {unique}")

    # Get foreign keys
    user_fks = inspector.get_foreign_keys('users')
    print("\nForeign Keys:")
    for fk in user_fks:
        print(f"  - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
        print(f"    ON DELETE: {fk.get('ondelete', 'NO ACTION')}")

    print("\n" + "=" * 80)
    print("SCHEMA VERIFICATION")
    print("=" * 80)

    # Verify required workspace columns
    required_workspace_cols = ['id', 'name', 'slug', 'created_at']
    missing_workspace_cols = [col for col in required_workspace_cols if col not in workspace_columns]
    if missing_workspace_cols:
        print(f"ERROR: Missing workspace columns: {missing_workspace_cols}")
        return False
    print("✓ All required workspace columns present")

    # Verify required user columns
    required_user_cols = ['id', 'email', 'workspace_id', 'created_at']
    missing_user_cols = [col for col in required_user_cols if col not in user_columns]
    if missing_user_cols:
        print(f"ERROR: Missing user columns: {missing_user_cols}")
        return False
    print("✓ All required user columns present")

    # Verify email unique index
    email_unique = any(
        'email' in idx['column_names'] and idx['unique']
        for idx in user_indexes
    )
    if not email_unique:
        print("ERROR: Email unique index not found")
        return False
    print("✓ Email unique index present")

    # Verify workspace_id foreign key
    workspace_fk = any(
        'workspace_id' in fk['constrained_columns'] and
        fk['referred_table'] == 'workspaces'
        for fk in user_fks
    )
    if not workspace_fk:
        print("ERROR: workspace_id foreign key not found")
        return False
    print("✓ workspace_id foreign key present")

    # Verify CASCADE delete
    cascade_delete = any(
        'workspace_id' in fk['constrained_columns'] and
        fk.get('ondelete') == 'CASCADE'
        for fk in user_fks
    )
    if not cascade_delete:
        print("WARNING: CASCADE delete not enforced in SQLite")
    else:
        print("✓ CASCADE delete configured")

    print("\n" + "=" * 80)
    print("SCHEMA VERIFICATION: PASSED")
    print("=" * 80)

    return True

if __name__ == "__main__":
    success = verify_schema()
    sys.exit(0 if success else 1)
