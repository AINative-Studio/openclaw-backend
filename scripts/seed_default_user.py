#!/usr/bin/env python3
"""
Seed Default User and Workspace

Creates a default workspace and user for initial setup.
Idempotent - safe to run multiple times.
"""

import sys
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.exc import IntegrityError
from backend.db.base import SessionLocal, init_db
from backend.models.workspace import Workspace
from backend.models.user import User


def seed_default_user():
    """
    Seed default workspace and user.

    Creates:
    - Default workspace (if not exists)
    - Default user linked to default workspace (if not exists)

    Returns:
        tuple: (workspace, user) objects
    """
    # Initialize database
    init_db()

    # Create session
    db = SessionLocal()

    try:
        # Default workspace configuration
        default_workspace_slug = "default-workspace"
        default_workspace_name = "Default Workspace"
        default_user_email = "admin@openclaw.local"

        print("=" * 80)
        print("SEEDING DEFAULT WORKSPACE AND USER")
        print("=" * 80)

        # Check if default workspace exists
        workspace = db.query(Workspace).filter(
            Workspace.slug == default_workspace_slug
        ).first()

        if workspace:
            print(f"\n✓ Default workspace already exists: {workspace.name}")
        else:
            # Create default workspace
            workspace = Workspace(
                id=uuid4(),
                name=default_workspace_name,
                slug=default_workspace_slug,
                description="Default workspace for OpenClaw backend"
            )
            db.add(workspace)
            db.commit()
            db.refresh(workspace)
            print(f"\n✓ Created default workspace: {workspace.name}")

        print(f"  - ID: {workspace.id}")
        print(f"  - Slug: {workspace.slug}")
        print(f"  - Created: {workspace.created_at}")

        # Check if default user exists
        user = db.query(User).filter(
            User.email == default_user_email
        ).first()

        if user:
            print(f"\n✓ Default user already exists: {user.email}")
        else:
            # Create default user
            user = User(
                id=uuid4(),
                email=default_user_email,
                workspace_id=workspace.id
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"\n✓ Created default user: {user.email}")

        print(f"  - ID: {user.id}")
        print(f"  - Email: {user.email}")
        print(f"  - Workspace ID: {user.workspace_id}")
        print(f"  - Created: {user.created_at}")

        print("\n" + "=" * 80)
        print("SEEDING COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"\nDefault User Email: {default_user_email}")
        print(f"Workspace: {default_workspace_name}")
        print("=" * 80)

        return workspace, user

    except IntegrityError as e:
        db.rollback()
        print(f"\nERROR: Database integrity error: {e}")
        print("This may indicate duplicate data or constraint violation.")
        return None, None

    except Exception as e:
        db.rollback()
        print(f"\nERROR: Unexpected error: {e}")
        return None, None

    finally:
        db.close()


if __name__ == "__main__":
    workspace, user = seed_default_user()

    # Exit with appropriate code
    if workspace and user:
        sys.exit(0)
    else:
        sys.exit(1)
