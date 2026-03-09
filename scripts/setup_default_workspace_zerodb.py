#!/usr/bin/env python3
"""
Setup ZeroDB Project for Default Workspace

Creates a ZeroDB project for the default workspace if it doesn't have one yet.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBClient


async def setup_workspace_zerodb():
    """Setup ZeroDB project for default workspace."""

    # Get database URL from environment or use default
    database_url = os.getenv("DATABASE_URL", "sqlite:///./openclaw.db")

    # Create engine and session
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
        echo=True
    )

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Get default workspace
        workspace = session.query(Workspace).filter(
            Workspace.slug == "default-workspace"
        ).first()

        if not workspace:
            print("Error: Default workspace not found. Run seed_default_workspace.py first.")
            return

        print(f"Found workspace: {workspace.name} (ID: {workspace.id})")

        # Check if already has ZeroDB project
        if workspace.zerodb_project_id:
            print(f"Workspace already has ZeroDB project: {workspace.zerodb_project_id}")
            return

        # Get ZeroDB API key
        zerodb_api_key = os.getenv("ZERODB_API_KEY")
        if not zerodb_api_key:
            print("Error: ZERODB_API_KEY not set in environment")
            return

        # Create ZeroDB client
        async with ZeroDBClient(api_key=zerodb_api_key) as client:
            # Create project
            print(f"Creating ZeroDB project for workspace '{workspace.name}'...")
            project = await client.create_project(
                name=f"workspace_{workspace.slug}",
                description=f"ZeroDB project for {workspace.name}"
            )

            print(f"Created ZeroDB project: {project}")

            # Update workspace with project ID
            workspace.zerodb_project_id = project["id"]
            session.commit()

            print(f"✓ Successfully set up ZeroDB project for workspace!")
            print(f"  Workspace ID: {workspace.id}")
            print(f"  ZeroDB Project ID: {workspace.zerodb_project_id}")

    except Exception as e:
        session.rollback()
        print(f"Error setting up ZeroDB project: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("Setting up ZeroDB project for default workspace...")
    print("-" * 60)

    asyncio.run(setup_workspace_zerodb())

    print("-" * 60)
    print("Setup complete!")
