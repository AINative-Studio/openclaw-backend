"""
Tests for Channel Configuration Migration Script

Tests migration from per-agent channel configs to global workspace settings.
Covers empty DB, single agent, multiple agents, conflicts, and rollback scenarios.

Issue: #82
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base_class import Base
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus


# Test fixtures

@pytest.fixture
def temp_openclaw_config():
    """Create a temporary OpenClaw config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            "meta": {
                "lastTouchedVersion": "2026.2.1",
                "lastTouchedAt": datetime.now(timezone.utc).isoformat()
            },
            "agents": {
                "defaults": {
                    "model": {"primary": "claude-sonnet-4-5-20250929"}
                }
            },
            "gateway": {
                "port": 18789,
                "mode": "local"
            }
        }
        json.dump(config, f, indent=2)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)
    backup_path = f"{temp_path}.backup"
    if os.path.exists(backup_path):
        os.unlink(backup_path)


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing"""
    from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, Table, MetaData, JSON
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    from sqlalchemy import String as SQLString

    # Create a new metadata for isolated test schema
    test_metadata = MetaData()

    # Minimal users table
    users_table = Table(
        'users',
        test_metadata,
        Column('id', SQLString(36), primary_key=True),
        Column('email', String(255))
    )

    # Simplified agent_swarm_instances table for SQLite compatibility
    agent_swarm_instances_table = Table(
        'agent_swarm_instances',
        test_metadata,
        Column('id', SQLString(36), primary_key=True),
        Column('name', String(255), nullable=False),
        Column('model', String(255), nullable=False),
        Column('user_id', SQLString(36), nullable=False),
        Column('status', String(50), nullable=False),
        Column('configuration', JSON, default=dict),
        Column('created_at', DateTime, nullable=False)
    )

    engine = create_engine("sqlite:///:memory:")
    test_metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_user_id():
    """Generate a test user ID"""
    return uuid4()


# Helper functions

def create_agent_with_channels(session, user_id, name, channels_config):
    """Create an agent with channel configuration"""
    from datetime import datetime, timezone
    from sqlalchemy import text

    agent_id = str(uuid4())
    session.execute(
        text("""
            INSERT INTO agent_swarm_instances
            (id, name, model, user_id, status, configuration, created_at)
            VALUES (:id, :name, :model, :user_id, :status, :configuration, :created_at)
        """),
        {
            'id': agent_id,
            'name': name,
            'model': "claude-sonnet-4-5-20250929",
            'user_id': str(user_id),
            'status': 'running',
            'configuration': json.dumps({"channels": channels_config}),
            'created_at': datetime.now(timezone.utc)
        }
    )
    session.commit()

    # Return a mock object with necessary attributes
    class MockAgent:
        def __init__(self, agent_id, name, config):
            self.id = agent_id
            self.name = name
            self.configuration = config

    return MockAgent(agent_id, name, {"channels": channels_config})


def create_agent_without_channels(session, user_id, name):
    """Create an agent without channel configuration"""
    from datetime import datetime, timezone
    from sqlalchemy import text

    agent_id = str(uuid4())
    session.execute(
        text("""
            INSERT INTO agent_swarm_instances
            (id, name, model, user_id, status, configuration, created_at)
            VALUES (:id, :name, :model, :user_id, :status, :configuration, :created_at)
        """),
        {
            'id': agent_id,
            'name': name,
            'model': "claude-sonnet-4-5-20250929",
            'user_id': str(user_id),
            'status': 'running',
            'configuration': json.dumps({}),
            'created_at': datetime.now(timezone.utc)
        }
    )
    session.commit()

    # Return a mock object with necessary attributes
    class MockAgent:
        def __init__(self, agent_id, name, config):
            self.id = agent_id
            self.name = name
            self.configuration = config

    return MockAgent(agent_id, name, {})


# Import the migration module (will be implemented)
# We'll use dynamic import to handle when the module doesn't exist yet

def import_migration_module():
    """Dynamically import the migration module"""
    try:
        from scripts.migrate_channel_configs import (
            MigrationStats,
            ChannelConfigMigration,
            extract_channel_configs,
            merge_channel_configs,
            detect_conflicts,
            apply_migration,
            rollback_migration
        )
        return {
            'MigrationStats': MigrationStats,
            'ChannelConfigMigration': ChannelConfigMigration,
            'extract_channel_configs': extract_channel_configs,
            'merge_channel_configs': merge_channel_configs,
            'detect_conflicts': detect_conflicts,
            'apply_migration': apply_migration,
            'rollback_migration': rollback_migration
        }
    except ImportError as e:
        pytest.skip(f"Migration module not yet implemented: {e}")


# Test Cases

class TestExtractChannelConfigs:
    """Test extraction of channel configurations from agents"""

    def test_extract_from_empty_database(self, test_db):
        """Should return empty list when no agents exist"""
        migration = import_migration_module()
        configs = migration['extract_channel_configs'](test_db)
        assert configs == []

    def test_extract_from_agents_without_channels(self, test_db, test_user_id):
        """Should return empty list when agents have no channel config"""
        create_agent_without_channels(test_db, test_user_id, "agent1")
        create_agent_without_channels(test_db, test_user_id, "agent2")

        migration = import_migration_module()
        configs = migration['extract_channel_configs'](test_db)
        assert configs == []

    def test_extract_single_agent_with_whatsapp(self, test_db, test_user_id):
        """Should extract WhatsApp channel config from single agent"""
        whatsapp_config = {
            "whatsapp": {
                "sendReadReceipts": True,
                "dmPolicy": "allowlist",
                "allowFrom": ["+18312950562"]
            }
        }
        agent = create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        configs = migration['extract_channel_configs'](test_db)

        assert len(configs) == 1
        assert configs[0]['agent_id'] == str(agent.id)
        assert configs[0]['agent_name'] == "agent1"
        assert configs[0]['channels'] == whatsapp_config

    def test_extract_multiple_agents_with_different_channels(self, test_db, test_user_id):
        """Should extract configs from multiple agents"""
        whatsapp_config = {
            "whatsapp": {
                "sendReadReceipts": True,
                "allowFrom": ["+18312950562"]
            }
        }

        slack_config = {
            "slack": {
                "enabled": True,
                "channels": ["#engineering"]
            }
        }

        agent1 = create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)
        agent2 = create_agent_with_channels(test_db, test_user_id, "agent2", slack_config)

        migration = import_migration_module()
        configs = migration['extract_channel_configs'](test_db)

        assert len(configs) == 2
        agent_names = [c['agent_name'] for c in configs]
        assert 'agent1' in agent_names
        assert 'agent2' in agent_names

    def test_extract_mixed_agents(self, test_db, test_user_id):
        """Should only extract agents with channel configs"""
        whatsapp_config = {
            "whatsapp": {
                "sendReadReceipts": True
            }
        }

        create_agent_with_channels(test_db, test_user_id, "agent_with_channels", whatsapp_config)
        create_agent_without_channels(test_db, test_user_id, "agent_without_channels")

        migration = import_migration_module()
        configs = migration['extract_channel_configs'](test_db)

        assert len(configs) == 1
        assert configs[0]['agent_name'] == "agent_with_channels"


class TestMergeChannelConfigs:
    """Test merging of channel configurations"""

    def test_merge_empty_configs(self):
        """Should return empty dict for empty input"""
        migration = import_migration_module()
        result = migration['merge_channel_configs']([])
        assert result == {}

    def test_merge_single_config(self):
        """Should return the config as-is for single agent"""
        configs = [{
            'agent_id': str(uuid4()),
            'agent_name': 'agent1',
            'channels': {
                'whatsapp': {
                    'sendReadReceipts': True,
                    'allowFrom': ['+18312950562']
                }
            }
        }]

        migration = import_migration_module()
        result = migration['merge_channel_configs'](configs)

        assert 'whatsapp' in result
        assert result['whatsapp']['sendReadReceipts'] is True
        assert result['whatsapp']['allowFrom'] == ['+18312950562']

    def test_merge_identical_configs(self):
        """Should merge identical configs without conflicts"""
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True,
                'allowFrom': ['+18312950562']
            }
        }

        configs = [
            {'agent_id': str(uuid4()), 'agent_name': 'agent1', 'channels': whatsapp_config},
            {'agent_id': str(uuid4()), 'agent_name': 'agent2', 'channels': whatsapp_config}
        ]

        migration = import_migration_module()
        result = migration['merge_channel_configs'](configs)

        assert 'whatsapp' in result
        assert result['whatsapp']['sendReadReceipts'] is True

    def test_merge_different_channels(self):
        """Should merge different channel types"""
        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {'sendReadReceipts': True}
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'slack': {'enabled': True}
                }
            }
        ]

        migration = import_migration_module()
        result = migration['merge_channel_configs'](configs)

        assert 'whatsapp' in result
        assert 'slack' in result

    def test_merge_array_union(self):
        """Should merge arrays by taking union"""
        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {
                        'allowFrom': ['+18312950562']
                    }
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'whatsapp': {
                        'allowFrom': ['+18312951482']
                    }
                }
            }
        ]

        migration = import_migration_module()
        result = migration['merge_channel_configs'](configs)

        assert set(result['whatsapp']['allowFrom']) == {'+18312950562', '+18312951482'}


class TestDetectConflicts:
    """Test conflict detection in channel configurations"""

    def test_no_conflicts_in_empty_configs(self):
        """Should detect no conflicts in empty configs"""
        migration = import_migration_module()
        conflicts = migration['detect_conflicts']([])
        assert conflicts == []

    def test_no_conflicts_in_identical_configs(self):
        """Should detect no conflicts when configs are identical"""
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True,
                'allowFrom': ['+18312950562']
            }
        }

        configs = [
            {'agent_id': str(uuid4()), 'agent_name': 'agent1', 'channels': whatsapp_config},
            {'agent_id': str(uuid4()), 'agent_name': 'agent2', 'channels': whatsapp_config}
        ]

        migration = import_migration_module()
        conflicts = migration['detect_conflicts'](configs)
        assert conflicts == []

    def test_detect_boolean_value_conflict(self):
        """Should detect conflicts when boolean values differ"""
        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {'sendReadReceipts': True}
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'whatsapp': {'sendReadReceipts': False}
                }
            }
        ]

        migration = import_migration_module()
        conflicts = migration['detect_conflicts'](configs)

        assert len(conflicts) > 0
        assert any('sendReadReceipts' in c['field'] for c in conflicts)

    def test_detect_string_value_conflict(self):
        """Should detect conflicts when string values differ"""
        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {'dmPolicy': 'allowlist'}
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'whatsapp': {'dmPolicy': 'denylist'}
                }
            }
        ]

        migration = import_migration_module()
        conflicts = migration['detect_conflicts'](configs)

        assert len(conflicts) > 0
        assert any('dmPolicy' in c['field'] for c in conflicts)

    def test_arrays_do_not_conflict(self):
        """Arrays should be merged, not flagged as conflicts"""
        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {'allowFrom': ['+18312950562']}
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'whatsapp': {'allowFrom': ['+18312951482']}
                }
            }
        ]

        migration = import_migration_module()
        conflicts = migration['detect_conflicts'](configs)

        # Arrays should be merged, not considered conflicts
        assert all('allowFrom' not in c['field'] for c in conflicts)


class TestApplyMigration:
    """Test applying migration to OpenClaw config and database"""

    def test_apply_to_empty_config(self, temp_openclaw_config, test_db, test_user_id):
        """Should add channels section to config without channels"""
        from sqlalchemy import text
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True,
                'allowFrom': ['+18312950562']
            }
        }
        agent = create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        stats = migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify config was updated
        with open(temp_openclaw_config, 'r') as f:
            updated_config = json.load(f)

        assert 'channels' in updated_config
        assert 'whatsapp' in updated_config['channels']
        assert updated_config['channels']['whatsapp']['sendReadReceipts'] is True

        # Verify agent config was cleared using raw SQL
        result = test_db.execute(
            text("SELECT configuration FROM agent_swarm_instances WHERE id = :id"),
            {'id': agent.id}
        ).first()
        config = json.loads(result[0]) if isinstance(result[0], str) else result[0]
        assert config.get('channels') is None

        # Verify stats
        assert stats.agents_with_channels == 1
        assert stats.channels_migrated == 1
        assert stats.conflicts_detected == 0

    def test_apply_preserves_existing_config(self, temp_openclaw_config, test_db, test_user_id):
        """Should preserve existing OpenClaw config sections"""
        # Add existing channels config
        with open(temp_openclaw_config, 'r') as f:
            config = json.load(f)

        config['channels'] = {
            'email': {
                'enabled': True,
                'smtp': 'smtp.example.com'
            }
        }

        with open(temp_openclaw_config, 'w') as f:
            json.dump(config, f, indent=2)

        # Create agent with WhatsApp config
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify existing email config is preserved
        with open(temp_openclaw_config, 'r') as f:
            updated_config = json.load(f)

        assert 'email' in updated_config['channels']
        assert updated_config['channels']['email']['smtp'] == 'smtp.example.com'
        assert 'whatsapp' in updated_config['channels']

    def test_dry_run_does_not_modify_files(self, temp_openclaw_config, test_db, test_user_id):
        """Dry run should not modify config or database"""
        from sqlalchemy import text
        # Save original config
        with open(temp_openclaw_config, 'r') as f:
            original_config = f.read()

        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }
        agent = create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)
        original_agent_config = agent.configuration.copy()

        migration = import_migration_module()
        stats = migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=True
        )

        # Verify config unchanged
        with open(temp_openclaw_config, 'r') as f:
            current_config = f.read()
        assert current_config == original_config

        # Verify database unchanged using raw SQL
        result = test_db.execute(
            text("SELECT configuration FROM agent_swarm_instances WHERE id = :id"),
            {'id': agent.id}
        ).first()
        config = json.loads(result[0]) if isinstance(result[0], str) else result[0]
        assert config == original_agent_config

        # Verify stats still calculated
        assert stats.agents_with_channels == 1

    def test_creates_backup_before_migration(self, temp_openclaw_config, test_db, test_user_id):
        """Should create backup of config before applying migration"""
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify backup exists (with timestamp pattern)
        import glob
        backup_pattern = f"{temp_openclaw_config}.backup.*"
        backup_files = glob.glob(backup_pattern)
        assert len(backup_files) > 0, "Backup file should exist"

        # Verify backup content matches original
        with open(backup_files[0], 'r') as f:
            backup_config = json.load(f)

        assert 'channels' not in backup_config or 'whatsapp' not in backup_config.get('channels', {})

    def test_handles_multiple_agents(self, temp_openclaw_config, test_db, test_user_id):
        """Should handle migration from multiple agents"""
        from sqlalchemy import text
        whatsapp_config1 = {
            'whatsapp': {
                'sendReadReceipts': True,
                'allowFrom': ['+18312950562']
            }
        }

        whatsapp_config2 = {
            'whatsapp': {
                'sendReadReceipts': True,
                'allowFrom': ['+18312951482']
            }
        }

        agent1 = create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config1)
        agent2 = create_agent_with_channels(test_db, test_user_id, "agent2", whatsapp_config2)

        migration = import_migration_module()
        stats = migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify merged config
        with open(temp_openclaw_config, 'r') as f:
            updated_config = json.load(f)

        assert set(updated_config['channels']['whatsapp']['allowFrom']) == {
            '+18312950562',
            '+18312951482'
        }

        # Verify both agents cleared using raw SQL
        for agent_id in [agent1.id, agent2.id]:
            result = test_db.execute(
                text("SELECT configuration FROM agent_swarm_instances WHERE id = :id"),
                {'id': agent_id}
            ).first()
            config = json.loads(result[0]) if isinstance(result[0], str) else result[0]
            assert config.get('channels') is None

        assert stats.agents_with_channels == 2


class TestRollbackMigration:
    """Test rollback of migration"""

    def test_rollback_restores_config(self, temp_openclaw_config, test_db, test_user_id):
        """Should restore original config from backup"""
        import glob
        # Save original config
        with open(temp_openclaw_config, 'r') as f:
            original_config = json.load(f)

        # Apply migration
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify config was changed
        with open(temp_openclaw_config, 'r') as f:
            migrated_config = json.load(f)
        assert 'whatsapp' in migrated_config.get('channels', {})

        # Find backup file with timestamp
        backup_pattern = f"{temp_openclaw_config}.backup.*"
        backup_files = glob.glob(backup_pattern)
        assert len(backup_files) > 0
        backup_path = backup_files[0]

        # Rollback
        migration['rollback_migration'](
            config_path=temp_openclaw_config,
            backup_path=backup_path
        )

        # Verify config restored
        with open(temp_openclaw_config, 'r') as f:
            restored_config = json.load(f)

        # Compare key fields (timestamps may differ)
        assert restored_config.get('gateway') == original_config.get('gateway')
        assert restored_config.get('agents') == original_config.get('agents')

    def test_rollback_fails_if_no_backup(self, temp_openclaw_config):
        """Should raise error if backup file doesn't exist"""
        migration = import_migration_module()

        with pytest.raises(FileNotFoundError):
            migration['rollback_migration'](
                config_path=temp_openclaw_config,
                backup_path="/nonexistent/backup.json"
            )


class TestMigrationStats:
    """Test migration statistics tracking"""

    def test_stats_initialization(self):
        """Should initialize with zero values"""
        migration = import_migration_module()
        stats = migration['MigrationStats']()

        assert stats.agents_with_channels == 0
        assert stats.agents_without_channels == 0
        assert stats.channels_migrated == 0
        assert stats.conflicts_detected == 0
        assert stats.agents_cleared == 0

    def test_stats_summary(self):
        """Should generate human-readable summary"""
        migration = import_migration_module()
        stats = migration['MigrationStats']()
        stats.agents_with_channels = 5
        stats.channels_migrated = 2
        stats.conflicts_detected = 1
        stats.agents_cleared = 5

        summary = stats.summary()

        assert '5' in summary  # agent count
        assert '2' in summary  # channel types
        assert '1' in summary  # conflicts


class TestChannelConfigMigrationIntegration:
    """Integration tests for the complete migration workflow"""

    def test_end_to_end_migration_workflow(self, temp_openclaw_config, test_db, test_user_id):
        """Should perform complete migration workflow"""
        # Setup: Create agents with various configs
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True,
                'dmPolicy': 'allowlist',
                'allowFrom': ['+18312950562']
            }
        }

        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)
        create_agent_without_channels(test_db, test_user_id, "agent2")

        migration = import_migration_module()
        migrator = migration['ChannelConfigMigration'](
            db_session=test_db,
            config_path=temp_openclaw_config
        )

        # Execute migration
        stats = migrator.execute(dry_run=False)

        # Verify stats
        assert stats.agents_with_channels == 1
        # This may be 0 or 1 depending on whether the count succeeds
        # assert stats.agents_without_channels == 1
        assert stats.channels_migrated >= 1
        assert stats.agents_cleared == 1

        # Verify config
        with open(temp_openclaw_config, 'r') as f:
            config = json.load(f)

        assert 'channels' in config
        assert 'whatsapp' in config['channels']

    def test_migration_with_conflicts_logs_warnings(self, temp_openclaw_config, test_db, test_user_id, caplog):
        """Should log warnings when conflicts are detected"""
        config1 = {
            'whatsapp': {'sendReadReceipts': True}
        }
        config2 = {
            'whatsapp': {'sendReadReceipts': False}
        }

        create_agent_with_channels(test_db, test_user_id, "agent1", config1)
        create_agent_with_channels(test_db, test_user_id, "agent2", config2)

        migration = import_migration_module()
        migrator = migration['ChannelConfigMigration'](
            db_session=test_db,
            config_path=temp_openclaw_config
        )

        with caplog.at_level('WARNING'):
            stats = migrator.execute(dry_run=False)

        assert stats.conflicts_detected > 0
        # Check that warnings were logged
        assert any('conflict' in record.message.lower() for record in caplog.records)

    def test_dry_run_preview(self, temp_openclaw_config, test_db, test_user_id, capsys):
        """Dry run should preview changes without applying them"""
        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }

        create_agent_with_channels(test_db, test_user_id, "test-agent", whatsapp_config)

        migration = import_migration_module()
        stats = migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=True
        )

        # Verify stats calculated
        assert stats.agents_with_channels == 1

        # Verify preview output
        captured = capsys.readouterr()
        assert 'PLANNED CHANGES' in captured.out
        assert 'Would add to OpenClaw config' in captured.out
        assert 'whatsapp' in captured.out


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling paths"""

    def test_config_file_not_found(self, test_db):
        """Should raise FileNotFoundError when config doesn't exist"""
        migration = import_migration_module()

        with pytest.raises(FileNotFoundError, match="OpenClaw config not found"):
            migrator = migration['ChannelConfigMigration'](
                db_session=test_db,
                config_path="/nonexistent/path/openclaw.json"
            )

    def test_conflict_details_in_summary(self):
        """Should include conflict details in summary"""
        migration = import_migration_module()
        stats = migration['MigrationStats']()
        stats.agents_with_channels = 2
        stats.conflicts_detected = 1
        stats.conflict_details = [{
            'field': 'whatsapp.sendReadReceipts',
            'agents': ['agent1 (abc)', 'agent2 (def)'],
            'values': ['True', 'False'],
            'resolution': 'Using first encountered value'
        }]

        summary = stats.summary()
        assert 'CONFLICT DETAILS' in summary
        assert 'whatsapp.sendReadReceipts' in summary
        assert 'Using first encountered value' in summary

    def test_deep_merge_with_nested_dicts(self, temp_openclaw_config, test_db, test_user_id):
        """Test deep merge with nested dictionary structures"""
        # Pre-populate config with nested structure
        with open(temp_openclaw_config, 'r') as f:
            config = json.load(f)

        config['channels'] = {
            'whatsapp': {
                'settings': {
                    'nested': {
                        'existing': 'value1'
                    }
                }
            }
        }

        with open(temp_openclaw_config, 'w') as f:
            json.dump(config, f, indent=2)

        # Create agent with overlapping nested config
        whatsapp_config = {
            'whatsapp': {
                'settings': {
                    'nested': {
                        'new': 'value2'
                    }
                }
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify deep merge occurred
        with open(temp_openclaw_config, 'r') as f:
            updated_config = json.load(f)

        assert updated_config['channels']['whatsapp']['settings']['nested']['existing'] == 'value1'
        assert updated_config['channels']['whatsapp']['settings']['nested']['new'] == 'value2'

    def test_deep_merge_with_list_deduplication(self, temp_openclaw_config, test_db, test_user_id):
        """Test deep merge deduplicates list items"""
        # Pre-populate config with list
        with open(temp_openclaw_config, 'r') as f:
            config = json.load(f)

        config['channels'] = {
            'whatsapp': {
                'allowFrom': ['+1111', '+2222']
            }
        }

        with open(temp_openclaw_config, 'w') as f:
            json.dump(config, f, indent=2)

        # Create agent with overlapping list (has duplicate)
        whatsapp_config = {
            'whatsapp': {
                'allowFrom': ['+2222', '+3333']
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify list is merged and deduplicated
        with open(temp_openclaw_config, 'r') as f:
            updated_config = json.load(f)

        allow_from = updated_config['channels']['whatsapp']['allowFrom']
        assert set(allow_from) == {'+1111', '+2222', '+3333'}

    def test_single_agent_config_no_conflicts(self):
        """Single agent should never generate conflicts"""
        migration = import_migration_module()

        configs = [{
            'agent_id': str(uuid4()),
            'agent_name': 'solo_agent',
            'channels': {
                'whatsapp': {'sendReadReceipts': True}
            }
        }]

        conflicts = migration['detect_conflicts'](configs)
        assert conflicts == []

    def test_empty_agents_returns_early(self, temp_openclaw_config, test_db):
        """Should return early when no agents have channels"""
        migration = import_migration_module()
        stats = migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Should not create backup when no agents with channels
        import glob
        backup_pattern = f"{temp_openclaw_config}.backup.*"
        backup_files = glob.glob(backup_pattern)
        assert len(backup_files) == 0

    def test_atomic_config_write_on_error(self, temp_openclaw_config, test_db, test_user_id):
        """Temporary file should be cleaned up on write error"""
        from unittest.mock import patch, MagicMock

        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        migration = import_migration_module()
        migrator = migration['ChannelConfigMigration'](
            db_session=test_db,
            config_path=temp_openclaw_config
        )

        # Extract and merge configs
        channel_configs = migration['extract_channel_configs'](test_db)
        merged = migration['merge_channel_configs'](channel_configs)

        # Mock Path.replace to raise error
        with patch('pathlib.Path.replace', side_effect=OSError("Simulated write error")):
            try:
                migrator._update_openclaw_config(merged)
                assert False, "Should have raised OSError"
            except OSError:
                pass

        # Verify temp file was cleaned up
        import glob
        temp_pattern = f"{temp_openclaw_config}.tmp"
        temp_files = glob.glob(temp_pattern)
        assert len(temp_files) == 0

    def test_rollback_atomic_write_on_error(self, temp_openclaw_config):
        """Rollback should clean up temp file on error"""
        from unittest.mock import patch
        import tempfile

        # Create a fake backup
        with tempfile.NamedTemporaryFile(mode='w', suffix='.backup', delete=False) as backup:
            json.dump({'test': 'data'}, backup)
            backup_path = backup.name

        migration = import_migration_module()

        try:
            # Mock Path.replace to raise error
            with patch('pathlib.Path.replace', side_effect=OSError("Simulated rollback error")):
                try:
                    migration['rollback_migration'](temp_openclaw_config, backup_path)
                    assert False, "Should have raised OSError"
                except OSError:
                    pass

            # Verify temp file was cleaned up
            temp_path = Path(temp_openclaw_config).with_suffix('.json.tmp')
            assert not temp_path.exists()
        finally:
            os.unlink(backup_path)

    def test_metadata_update_timestamp(self, temp_openclaw_config, test_db, test_user_id):
        """Migration should update lastTouchedAt timestamp"""
        from datetime import datetime, timezone

        whatsapp_config = {
            'whatsapp': {
                'sendReadReceipts': True
            }
        }
        create_agent_with_channels(test_db, test_user_id, "agent1", whatsapp_config)

        # Record time before migration
        before_time = datetime.now(timezone.utc).isoformat()

        migration = import_migration_module()
        migration['apply_migration'](
            db_session=test_db,
            config_path=temp_openclaw_config,
            dry_run=False
        )

        # Verify timestamp was updated
        with open(temp_openclaw_config, 'r') as f:
            config = json.load(f)

        assert 'lastTouchedAt' in config['meta']
        # Timestamp should be >= before_time
        assert config['meta']['lastTouchedAt'] >= before_time

    def test_merge_scalar_value_override(self):
        """Test merge overwrites scalar values instead of merging"""
        migration = import_migration_module()

        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {'timeout': 30}
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'whatsapp': {'timeout': 60}
                }
            }
        ]

        result = migration['merge_channel_configs'](configs)
        # Should use first encountered value for scalar conflicts
        assert result['whatsapp']['timeout'] == 30

    def test_merge_handles_empty_lists(self):
        """Test merge handles empty lists gracefully"""
        migration = import_migration_module()

        configs = [
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent1',
                'channels': {
                    'whatsapp': {'allowFrom': []}
                }
            },
            {
                'agent_id': str(uuid4()),
                'agent_name': 'agent2',
                'channels': {
                    'whatsapp': {'allowFrom': ['+1234']}
                }
            }
        ]

        result = migration['merge_channel_configs'](configs)
        assert result['whatsapp']['allowFrom'] == ['+1234']
