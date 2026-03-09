#!/usr/bin/env python3
"""
Data Migration Script: Link Agents to Default Workspace

Migrates existing AgentSwarmInstance records without workspace_id
to a default workspace. Supports both real migration and dry-run mode.

Usage:
    python scripts/migrate_agents_to_default_workspace.py [--dry-run] [--workspace-slug SLUG]

Options:
    --dry-run          Show what would be migrated without making changes
    --workspace-slug   Slug of default workspace (default: "default")
"""

import argparse
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from backend.models.workspace import Workspace
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
from backend.models.user import User


def migrate_agents_to_workspace(
    database_url: str,
    workspace_slug: str = "default",
    dry_run: bool = False
) -> dict:
    """
    Migrate agents without workspace_id to a default workspace.

    Args:
        database_url: SQLAlchemy database URL
        workspace_slug: Slug of the default workspace
        dry_run: If True, don't commit changes

    Returns:
        Dictionary with migration statistics
    """
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Find or create default workspace
        workspace = session.query(Workspace).filter(
            Workspace.slug == workspace_slug
        ).first()

        if not workspace:
            if dry_run:
                print(f"[DRY RUN] Would create workspace with slug '{workspace_slug}'")
                # Can't continue dry run without workspace
                return {
                    "status": "error",
                    "message": f"Workspace '{workspace_slug}' not found. Run without --dry-run to create it.",
                    "migrated_count": 0
                }
            else:
                workspace = Workspace(
                    name="Default Workspace",
                    slug=workspace_slug,
                    description="Default workspace for migrated agents"
                )
                session.add(workspace)
                session.flush()  # Get the workspace ID
                print(f"Created default workspace: {workspace.name} ({workspace.slug})")

        # Find agents without workspace_id
        agents_without_workspace = session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.workspace_id.is_(None)
        ).all()

        if not agents_without_workspace:
            print("No agents found without workspace_id")
            return {
                "status": "success",
                "message": "No migration needed",
                "migrated_count": 0
            }

        print(f"Found {len(agents_without_workspace)} agents without workspace_id")

        # Migrate each agent
        migrated_count = 0
        for agent in agents_without_workspace:
            if dry_run:
                print(f"[DRY RUN] Would link agent '{agent.name}' (ID: {agent.id}) to workspace '{workspace.slug}'")
            else:
                agent.workspace_id = workspace.id
                print(f"Linked agent '{agent.name}' (ID: {agent.id}) to workspace '{workspace.slug}'")
            migrated_count += 1

        # Commit changes
        if not dry_run:
            session.commit()
            print(f"\nSuccessfully migrated {migrated_count} agents to workspace '{workspace.slug}'")
        else:
            print(f"\n[DRY RUN] Would migrate {migrated_count} agents (no changes committed)")

        return {
            "status": "success",
            "message": f"Migrated {migrated_count} agents",
            "migrated_count": migrated_count,
            "workspace_slug": workspace_slug,
            "dry_run": dry_run
        }

    except Exception as e:
        session.rollback()
        print(f"Error during migration: {e}", file=sys.stderr)
        return {
            "status": "error",
            "message": str(e),
            "migrated_count": 0
        }
    finally:
        session.close()


def main():
    """Main entry point for migration script"""
    parser = argparse.ArgumentParser(
        description="Migrate agents to default workspace"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes"
    )
    parser.add_argument(
        "--workspace-slug",
        default="default",
        help="Slug of default workspace (default: 'default')"
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL (defaults to DATABASE_URL env var or sqlite:///./openclaw.db)"
    )

    args = parser.parse_args()

    # Determine database URL
    if args.database_url:
        database_url = args.database_url
    else:
        import os
        database_url = os.getenv("DATABASE_URL", "sqlite:///./openclaw.db")

    print(f"Database: {database_url}")
    print(f"Workspace slug: {args.workspace_slug}")
    print(f"Dry run: {args.dry_run}")
    print("-" * 60)

    # Run migration
    result = migrate_agents_to_workspace(
        database_url=database_url,
        workspace_slug=args.workspace_slug,
        dry_run=args.dry_run
    )

    # Exit with appropriate status code
    if result["status"] == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
