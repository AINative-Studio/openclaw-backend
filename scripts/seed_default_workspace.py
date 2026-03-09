#!/usr/bin/env python3
"""
Seed Default Workspace Script

Creates a default workspace for development and testing purposes.
Uses SQLAlchemy ORM to create workspace with ZeroDB integration support.

Usage:
    python scripts/seed_default_workspace.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

from backend.db.base_class import Base
from backend.models.workspace import Workspace


def seed_default_workspace():
    """
    Create default workspace for development and testing.

    Returns:
        Workspace: The created workspace instance
    """
    # Get database URL from environment or use default
    database_url = os.getenv("DATABASE_URL", "sqlite:///./openclaw.db")

    # Create engine and session
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
        echo=True
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Check if default workspace already exists
        existing_workspace = session.query(Workspace).filter(
            Workspace.slug == "default-workspace"
        ).first()

        if existing_workspace:
            print(f"Default workspace already exists: {existing_workspace.name} (ID: {existing_workspace.id})")
            return existing_workspace

        # Create default workspace
        default_workspace = Workspace(
            id=uuid4(),
            name="Default Workspace",
            slug="default-workspace",
            description="Default workspace for OpenClaw development and testing",
            zerodb_project_id=None  # Will be set when ZeroDB is integrated
        )

        session.add(default_workspace)
        session.commit()
        session.refresh(default_workspace)

        print(f"Successfully created default workspace:")
        print(f"  ID: {default_workspace.id}")
        print(f"  Name: {default_workspace.name}")
        print(f"  Slug: {default_workspace.slug}")
        print(f"  Description: {default_workspace.description}")
        print(f"  Created At: {default_workspace.created_at}")

        return default_workspace

    except Exception as e:
        session.rollback()
        print(f"Error creating default workspace: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("Seeding default workspace...")
    print("-" * 60)

    workspace = seed_default_workspace()

    print("-" * 60)
    print("Seeding complete!")
