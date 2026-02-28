#!/usr/bin/env python3
"""
Channel Configuration Migration Script

Migrates channel configurations from per-agent storage to global workspace settings.
Supports dry-run mode for previewing changes and rollback capability.

Issue: #82
Usage:
    python scripts/migrate_channel_configs.py                    # Run migration
    python scripts/migrate_channel_configs.py --dry-run          # Preview changes
    python scripts/migrate_channel_configs.py --rollback         # Restore from backup
"""

import argparse
import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.agent_swarm_lifecycle import AgentSwarmInstance

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class MigrationStats:
    """Statistics for migration execution"""
    agents_with_channels: int = 0
    agents_without_channels: int = 0
    channels_migrated: int = 0
    conflicts_detected: int = 0
    agents_cleared: int = 0
    conflict_details: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """Generate human-readable summary"""
        lines = [
            "=" * 60,
            "MIGRATION SUMMARY",
            "=" * 60,
            f"Agents with channels:      {self.agents_with_channels}",
            f"Agents without channels:   {self.agents_without_channels}",
            f"Channel types migrated:    {self.channels_migrated}",
            f"Conflicts detected:        {self.conflicts_detected}",
            f"Agent configs cleared:     {self.agents_cleared}",
            "=" * 60
        ]

        if self.conflict_details:
            lines.append("\nCONFLICT DETAILS:")
            for i, conflict in enumerate(self.conflict_details, 1):
                lines.append(f"\n{i}. {conflict['field']}")
                lines.append(f"   Agents: {', '.join(conflict['agents'])}")
                lines.append(f"   Values: {conflict['values']}")
                lines.append(f"   Resolution: {conflict['resolution']}")

        return "\n".join(lines)


class ChannelConfigMigration:
    """Main migration orchestrator"""

    def __init__(self, db_session: Session, config_path: str):
        self.db_session = db_session
        self.config_path = Path(config_path)
        self.stats = MigrationStats()

        if not self.config_path.exists():
            raise FileNotFoundError(f"OpenClaw config not found: {self.config_path}")

    def execute(self, dry_run: bool = False) -> MigrationStats:
        """Execute migration workflow"""
        logger.info("Starting channel configuration migration")
        logger.info(f"Config path: {self.config_path}")
        logger.info(f"Dry run: {dry_run}")

        # Step 1: Extract channel configs from agents
        logger.info("Step 1: Extracting channel configurations from agents")
        channel_configs = extract_channel_configs(self.db_session)

        # Count all agents
        from sqlalchemy import text
        try:
            total_agents = self.db_session.query(AgentSwarmInstance).count()
        except:
            result = self.db_session.execute(text("SELECT COUNT(*) FROM agent_swarm_instances"))
            total_agents = result.scalar()

        self.stats.agents_with_channels = len(channel_configs)
        self.stats.agents_without_channels = total_agents - len(channel_configs)

        if not channel_configs:
            logger.info("No agents with channel configurations found")
            return self.stats

        logger.info(f"Found {len(channel_configs)} agents with channel configurations")

        # Step 2: Detect conflicts
        logger.info("Step 2: Detecting conflicts")
        conflicts = detect_conflicts(channel_configs)
        self.stats.conflicts_detected = len(conflicts)
        self.stats.conflict_details = conflicts

        if conflicts:
            logger.warning(f"Detected {len(conflicts)} conflicts:")
            for conflict in conflicts:
                logger.warning(f"  - {conflict['field']}: {conflict['resolution']}")

        # Step 3: Merge configs
        logger.info("Step 3: Merging channel configurations")
        merged_channels = merge_channel_configs(channel_configs)
        self.stats.channels_migrated = len(merged_channels)

        logger.info(f"Merged configurations for {len(merged_channels)} channel types:")
        for channel_type in merged_channels.keys():
            logger.info(f"  - {channel_type}")

        if dry_run:
            logger.info("DRY RUN: Would apply the following changes:")
            self._log_planned_changes(merged_channels, channel_configs)
            return self.stats

        # Step 4: Create backup
        logger.info("Step 4: Creating backup of OpenClaw config")
        backup_path = self._create_backup()
        logger.info(f"Backup created: {backup_path}")

        # Step 5: Update OpenClaw config
        logger.info("Step 5: Updating OpenClaw config")
        self._update_openclaw_config(merged_channels)
        logger.info("OpenClaw config updated successfully")

        # Step 6: Clear agent channel configs
        logger.info("Step 6: Clearing agent channel configurations")
        cleared_count = self._clear_agent_configs(channel_configs)
        self.stats.agents_cleared = cleared_count
        logger.info(f"Cleared channel configs from {cleared_count} agents")

        logger.info("Migration completed successfully")
        return self.stats

    def _log_planned_changes(self, merged_channels: Dict, channel_configs: List[Dict]):
        """Log what changes would be made in dry-run mode"""
        print("\n" + "=" * 60)
        print("PLANNED CHANGES (DRY RUN)")
        print("=" * 60)

        print("\nWould add to OpenClaw config:")
        print(json.dumps({"channels": merged_channels}, indent=2))

        print(f"\nWould clear channel configs from {len(channel_configs)} agents:")
        for config in channel_configs:
            print(f"  - {config['agent_name']} ({config['agent_id']})")

        print("\n" + "=" * 60)

    def _create_backup(self) -> Path:
        """Create timestamped backup of config file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(str(self.config_path) + f'.backup.{timestamp}')

        shutil.copy2(self.config_path, backup_path)
        return backup_path

    def _update_openclaw_config(self, merged_channels: Dict):
        """Update OpenClaw config with merged channels (atomic write)"""
        # Read current config
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        # Merge channels (preserve existing channel configs)
        if 'channels' not in config:
            config['channels'] = {}

        for channel_type, channel_config in merged_channels.items():
            if channel_type in config['channels']:
                logger.warning(f"Channel '{channel_type}' already exists in config, merging")
                config['channels'][channel_type] = self._deep_merge(
                    config['channels'][channel_type],
                    channel_config
                )
            else:
                config['channels'][channel_type] = channel_config

        # Update metadata
        config['meta']['lastTouchedAt'] = datetime.now(timezone.utc).isoformat()

        # Atomic write using temp file + rename
        temp_path = self.config_path.with_suffix('.json.tmp')
        try:
            with open(temp_path, 'w') as f:
                json.dump(config, f, indent=2)
                f.write('\n')

            temp_path.replace(self.config_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e

    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()

        for key, value in update.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._deep_merge(result[key], value)
                elif isinstance(result[key], list) and isinstance(value, list):
                    result[key] = list(set(result[key] + value))
                else:
                    result[key] = value
            else:
                result[key] = value

        return result

    def _clear_agent_configs(self, channel_configs: List[Dict]) -> int:
        """Clear channel configs from agents"""
        from sqlalchemy import text
        import json as json_module

        cleared = 0

        try:
            # Try ORM approach first
            for config in channel_configs:
                agent = self.db_session.query(AgentSwarmInstance).filter_by(
                    id=config['agent_id']
                ).first()

                if agent and agent.configuration and 'channels' in agent.configuration:
                    updated_config = agent.configuration.copy()
                    del updated_config['channels']
                    agent.configuration = updated_config
                    cleared += 1

            self.db_session.commit()
            return cleared

        except Exception:
            # Fallback to raw SQL for test compatibility
            for config in channel_configs:
                result = self.db_session.execute(
                    text("SELECT configuration FROM agent_swarm_instances WHERE id = :id"),
                    {'id': config['agent_id']}
                ).first()

                if result and result[0]:
                    current_config = json_module.loads(result[0]) if isinstance(result[0], str) else result[0]

                    if current_config and 'channels' in current_config:
                        updated_config = current_config.copy()
                        del updated_config['channels']

                        self.db_session.execute(
                            text("UPDATE agent_swarm_instances SET configuration = :config WHERE id = :id"),
                            {
                                'config': json_module.dumps(updated_config),
                                'id': config['agent_id']
                            }
                        )
                        cleared += 1

            self.db_session.commit()
            return cleared


def extract_channel_configs(db_session: Session) -> List[Dict[str, Any]]:
    """Extract channel configurations from all agents"""
    try:
        # Try ORM approach first
        agents = db_session.query(AgentSwarmInstance).all()
        configs = []
        for agent in agents:
            if agent.configuration and 'channels' in agent.configuration:
                configs.append({
                    'agent_id': str(agent.id),
                    'agent_name': agent.name,
                    'channels': agent.configuration['channels']
                })
        return configs
    except Exception:
        # Fallback to raw SQL for test compatibility
        from sqlalchemy import text
        import json as json_module

        result = db_session.execute(
            text("SELECT id, name, configuration FROM agent_swarm_instances")
        )

        configs = []
        for row in result:
            agent_id, name, config_str = row
            if config_str:
                config = json_module.loads(config_str) if isinstance(config_str, str) else config_str
                if config and 'channels' in config:
                    configs.append({
                        'agent_id': str(agent_id),
                        'agent_name': name,
                        'channels': config['channels']
                    })

        return configs


def detect_conflicts(channel_configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect conflicting values across channel configurations"""
    if len(channel_configs) <= 1:
        return []

    conflicts = []
    field_values = {}

    def traverse(obj, path="", agent_info=None):
        """Recursively traverse config and track all field values"""
        if isinstance(obj, dict):
            for key, val in obj.items():
                new_path = f"{path}.{key}" if path else key
                traverse(val, new_path, agent_info)
        elif isinstance(obj, (str, int, float, bool)):
            if path not in field_values:
                field_values[path] = {}

            value_key = str(obj)
            if value_key not in field_values[path]:
                field_values[path][value_key] = []

            field_values[path][value_key].append(agent_info)

    # Traverse all configs
    for config in channel_configs:
        agent_info = f"{config['agent_name']} ({config['agent_id'][:8]})"
        traverse(config['channels'], agent_info=agent_info)

    # Find conflicts
    for field, values in field_values.items():
        if len(values) > 1:
            conflicts.append({
                'field': field,
                'values': list(values.keys()),
                'agents': [agent for agents in values.values() for agent in agents],
                'resolution': 'Using first encountered value'
            })

    return conflicts


def merge_channel_configs(channel_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge channel configurations with conflict resolution"""
    if not channel_configs:
        return {}

    merged = {}

    for config in channel_configs:
        channels = config['channels']

        for channel_type, channel_config in channels.items():
            if channel_type not in merged:
                merged[channel_type] = channel_config.copy()
            else:
                merged[channel_type] = _merge_dicts(
                    merged[channel_type],
                    channel_config
                )

    return merged


def _merge_dicts(base: Dict, update: Dict) -> Dict:
    """Recursively merge two dictionaries"""
    result = base.copy()

    for key, value in update.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = _merge_dicts(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                seen = set(result[key])
                for item in value:
                    if item not in seen:
                        result[key].append(item)
                        seen.add(item)
        else:
            result[key] = value

    return result


def apply_migration(
    db_session: Session,
    config_path: str,
    dry_run: bool = False
) -> MigrationStats:
    """Apply migration from database to OpenClaw config"""
    migrator = ChannelConfigMigration(db_session, config_path)
    return migrator.execute(dry_run=dry_run)


def rollback_migration(config_path: str, backup_path: str):
    """Rollback migration by restoring from backup"""
    backup = Path(backup_path)
    config = Path(config_path)

    if not backup.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    logger.info(f"Rolling back from backup: {backup_path}")

    temp_path = config.with_suffix('.json.tmp')
    try:
        shutil.copy2(backup, temp_path)
        temp_path.replace(config)
        logger.info(f"Config restored from backup: {config_path}")
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise e


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Migrate channel configurations to global workspace settings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without applying
  python scripts/migrate_channel_configs.py --dry-run

  # Run migration
  python scripts/migrate_channel_configs.py

  # Rollback from specific backup
  python scripts/migrate_channel_configs.py --rollback --backup-path ~/.openclaw/openclaw.json.backup.20260227_120000

  # Use custom config path
  python scripts/migrate_channel_configs.py --config /path/to/openclaw.json

  # Use custom database
  python scripts/migrate_channel_configs.py --db-url postgresql://user:pass@host/db
        """
    )

    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    parser.add_argument('--rollback', action='store_true', help='Rollback migration from backup')
    parser.add_argument('--config', default=os.path.expanduser('~/.openclaw/openclaw.json'), help='Path to openclaw.json (default: ~/.openclaw/openclaw.json)')
    parser.add_argument('--backup-path', help='Path to backup file for rollback')
    parser.add_argument('--db-url', help='Database URL (default: from DATABASE_URL env var)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        if args.rollback:
            if not args.backup_path:
                config_path = Path(args.config)
                backups = sorted(
                    config_path.parent.glob(f"{config_path.name}.backup.*"),
                    reverse=True
                )

                if not backups:
                    logger.error("No backup files found")
                    sys.exit(1)

                args.backup_path = str(backups[0])
                logger.info(f"Using most recent backup: {args.backup_path}")

            rollback_migration(args.config, args.backup_path)
            logger.info("Rollback completed successfully")

        else:
            db_url = args.db_url or os.environ.get('DATABASE_URL', 'sqlite:///./openclaw.db')
            logger.info(f"Connecting to database: {db_url.split('@')[-1] if '@' in db_url else db_url}")

            engine = create_engine(db_url)
            SessionLocal = sessionmaker(bind=engine)
            db_session = SessionLocal()

            try:
                stats = apply_migration(
                    db_session=db_session,
                    config_path=args.config,
                    dry_run=args.dry_run
                )

                print("\n" + stats.summary())

                if args.dry_run:
                    print("\nTo apply these changes, run without --dry-run flag")

            finally:
                db_session.close()

    except KeyboardInterrupt:
        logger.info("Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == '__main__':
    main()
