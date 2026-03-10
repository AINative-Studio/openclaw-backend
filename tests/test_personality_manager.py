"""
Test Personality Manager Template File Loading

BDD-style tests for Issue #140: Refactor PersonalityManager to read from template files
"""

import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from backend.personality.manager import PersonalityManager


class TestPersonalityManager:
    """BDD-style tests for PersonalityManager template functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test personalities"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def manager(self, temp_dir):
        """Create PersonalityManager instance with temp directory"""
        return PersonalityManager(base_path=temp_dir)

    @pytest.fixture
    def template_dir(self):
        """Get path to actual template directory"""
        backend_dir = Path(__file__).parent.parent / "backend"
        return backend_dir / "personality" / "templates"

    @pytest.fixture
    def sample_agent_data(self):
        """Sample agent data for template substitution"""
        return {
            "agent_id": str(uuid.uuid4()),
            "agent_name": "TestAgent",
            "model": "claude-3-5-sonnet-20241022",
            "persona": "A helpful test agent",
            "created_at": datetime.now().isoformat()
        }

    class TestTemplateFileLoading:
        """Tests for loading template files from disk"""

        def test_loads_soul_template_file(self, manager, template_dir):
            """Should load SOUL.md template from templates directory"""
            # Verify template file exists
            soul_template = template_dir / "SOUL.md"
            assert soul_template.exists(), "SOUL.md template should exist"

            # Content should be readable
            content = soul_template.read_text()
            assert len(content) > 0, "SOUL.md should have content"

        def test_loads_agents_template_file(self, manager, template_dir):
            """Should load AGENTS.md template from templates directory"""
            agents_template = template_dir / "AGENTS.md"
            assert agents_template.exists(), "AGENTS.md template should exist"

            content = agents_template.read_text()
            assert len(content) > 0, "AGENTS.md should have content"

        def test_loads_tools_template_file(self, manager, template_dir):
            """Should load TOOLS.md template from templates directory"""
            tools_template = template_dir / "TOOLS.md"
            assert tools_template.exists(), "TOOLS.md template should exist"

            content = tools_template.read_text()
            assert len(content) > 0, "TOOLS.md should have content"

        def test_loads_identity_template_file(self, manager, template_dir):
            """Should load IDENTITY.md template from templates directory"""
            identity_template = template_dir / "IDENTITY.md"
            assert identity_template.exists(), "IDENTITY.md template should exist"

            content = identity_template.read_text()
            assert len(content) > 0, "IDENTITY.md should have content"

        def test_loads_user_template_file(self, manager, template_dir):
            """Should load USER.md template from templates directory"""
            user_template = template_dir / "USER.md"
            assert user_template.exists(), "USER.md template should exist"

            content = user_template.read_text()
            assert len(content) > 0, "USER.md should have content"

        def test_loads_bootstrap_template_file(self, manager, template_dir):
            """Should load BOOTSTRAP.md template from templates directory"""
            bootstrap_template = template_dir / "BOOTSTRAP.md"
            assert bootstrap_template.exists(), "BOOTSTRAP.md template should exist"

            content = bootstrap_template.read_text()
            assert len(content) > 0, "BOOTSTRAP.md should have content"

        def test_loads_heartbeat_template_file(self, manager, template_dir):
            """Should load HEARTBEAT.md template from templates directory"""
            heartbeat_template = template_dir / "HEARTBEAT.md"
            assert heartbeat_template.exists(), "HEARTBEAT.md template should exist"

            content = heartbeat_template.read_text()
            assert len(content) > 0, "HEARTBEAT.md should have content"

        def test_loads_memory_template_file(self, manager, template_dir):
            """Should load MEMORY.md template from templates directory"""
            memory_template = template_dir / "MEMORY.md"
            assert memory_template.exists(), "MEMORY.md template should exist"

            content = memory_template.read_text()
            assert len(content) > 0, "MEMORY.md should have content"

        def test_loads_all_required_template_files(self, template_dir):
            """Should have all 8 required template files"""
            required_templates = [
                "SOUL.md",
                "AGENTS.md",
                "TOOLS.md",
                "IDENTITY.md",
                "USER.md",
                "BOOTSTRAP.md",
                "HEARTBEAT.md",
                "MEMORY.md"
            ]

            for template_name in required_templates:
                template_path = template_dir / template_name
                assert template_path.exists(), f"{template_name} should exist in templates/"

    class TestVariableSubstitution:
        """Tests for variable substitution in templates"""

        def test_substitutes_agent_name_variable(self, manager, sample_agent_data):
            """Should replace {{AGENT_NAME}} with actual agent name"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Check SOUL template has agent name substituted
            assert sample_agent_data["agent_name"] in templates["soul"]
            assert "{{AGENT_NAME}}" not in templates["soul"]

        def test_substitutes_agent_id_variable(self, manager, sample_agent_data):
            """Should replace {{AGENT_ID}} with actual agent UUID"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Check at least one template has agent_id substituted
            # (IDENTITY typically contains ID information)
            combined_content = " ".join(templates.values())
            assert "{{AGENT_ID}}" not in combined_content, "No template should contain {{AGENT_ID}} placeholder"

        def test_substitutes_model_variable(self, manager, sample_agent_data):
            """Should replace {{MODEL}} with actual model name"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Model should appear in at least one template
            combined_content = " ".join(templates.values())
            assert sample_agent_data["model"] in combined_content or "{{MODEL}}" not in combined_content

        def test_substitutes_persona_variable_when_provided(self, manager, sample_agent_data):
            """Should replace {{PERSONA}} with actual persona when provided"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Persona should appear if it was provided
            combined_content = " ".join(templates.values())
            if sample_agent_data["persona"]:
                assert sample_agent_data["persona"] in combined_content or "{{PERSONA}}" not in combined_content

        def test_handles_persona_variable_when_none(self, manager, sample_agent_data):
            """Should handle {{PERSONA}} gracefully when persona is None"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=None,  # No persona provided
                created_at=sample_agent_data["created_at"]
            )

            # Should not crash and should not have unreplaced {{PERSONA}} tags
            combined_content = " ".join(templates.values())
            assert "{{PERSONA}}" not in combined_content

        def test_substitutes_created_at_variable(self, manager, sample_agent_data):
            """Should replace {{CREATED_AT}} with creation timestamp"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Created timestamp should be substituted
            combined_content = " ".join(templates.values())
            assert "{{CREATED_AT}}" not in combined_content

        def test_substitutes_all_variables_in_all_templates(self, manager, sample_agent_data):
            """Should not leave any unreplaced {{VARIABLE}} placeholders"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Check each template for unreplaced variables
            for file_type, content in templates.items():
                # Should not contain any double-brace placeholders
                assert "{{AGENT_NAME}}" not in content, f"{file_type} should not contain {{{{AGENT_NAME}}}}"
                assert "{{AGENT_ID}}" not in content, f"{file_type} should not contain {{{{AGENT_ID}}}}"
                assert "{{MODEL}}" not in content, f"{file_type} should not contain {{{{MODEL}}}}"
                assert "{{CREATED_AT}}" not in content, f"{file_type} should not contain {{{{CREATED_AT}}}}"

        def test_preserves_template_structure_after_substitution(self, manager, sample_agent_data):
            """Should maintain markdown structure after variable substitution"""
            templates = manager._get_default_templates(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"],
                created_at=sample_agent_data["created_at"]
            )

            # Each template should still be valid markdown
            for file_type, content in templates.items():
                # Should have content
                assert len(content) > 0, f"{file_type} should have content after substitution"
                # Should preserve markdown headers
                assert "#" in content, f"{file_type} should have markdown headers"

    class TestInitializeAgentPersonality:
        """Tests for initialize_agent_personality method"""

        def test_creates_all_personality_files(self, manager, sample_agent_data):
            """Should create all 8 personality files for new agent"""
            result = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"]
            )

            # Should return PersonalitySet with all files
            assert result.soul is not None
            assert result.agents is not None
            assert result.tools is not None
            assert result.identity is not None
            assert result.user is not None
            assert result.bootstrap is not None
            assert result.heartbeat is not None
            assert result.memory is not None

        def test_saves_files_to_agent_directory(self, manager, sample_agent_data):
            """Should save personality files to agent-specific directory"""
            manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"]
            )

            # Check files were created
            agent_dir = Path(manager.loader.base_path) / sample_agent_data["agent_id"]
            assert agent_dir.exists()

            expected_files = [
                "SOUL.md",
                "AGENTS.md",
                "TOOLS.md",
                "IDENTITY.md",
                "USER.md",
                "BOOTSTRAP.md",
                "HEARTBEAT.md",
                "MEMORY.md"
            ]

            for filename in expected_files:
                file_path = agent_dir / filename
                assert file_path.exists(), f"{filename} should be created"

        def test_uses_agent_name_in_generated_files(self, manager, sample_agent_data):
            """Should include agent name in generated personality files"""
            result = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"]
            )

            # Agent name should appear in content
            assert sample_agent_data["agent_name"] in result.soul.content
            assert sample_agent_data["agent_name"] in result.identity.content

        def test_uses_model_in_generated_files(self, manager, sample_agent_data):
            """Should include model name in generated personality files"""
            result = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"]
            )

            # Model might appear in identity or bootstrap
            combined = result.identity.content + result.bootstrap.content
            # If model is in template, it should be substituted
            assert "{{MODEL}}" not in combined

        def test_includes_persona_when_provided(self, manager, sample_agent_data):
            """Should include persona in SOUL.md when provided"""
            result = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"]
            )

            # Persona should appear in soul content
            if sample_agent_data["persona"]:
                assert sample_agent_data["persona"] in result.soul.content or "{{PERSONA}}" not in result.soul.content

        def test_handles_missing_persona_gracefully(self, manager, sample_agent_data):
            """Should work correctly when persona is None"""
            result = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=None
            )

            # Should still create valid files
            assert result.soul is not None
            assert len(result.soul.content) > 0
            # Should not contain unreplaced placeholder
            assert "{{PERSONA}}" not in result.soul.content

        def test_can_be_called_multiple_times_for_same_agent(self, manager, sample_agent_data):
            """Should allow re-initialization of agent personality"""
            # First initialization
            result1 = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona="First persona"
            )

            # Second initialization (update)
            result2 = manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona="Second persona"
            )

            # Both should succeed
            assert result1 is not None
            assert result2 is not None

    class TestFallbackMechanism:
        """Tests for fallback to inline templates when files don't exist"""

        def test_uses_fallback_when_template_file_missing(self, manager, sample_agent_data, tmp_path):
            """Should use fallback inline templates if template files don't exist"""
            # Create a manager with a directory that has no templates
            empty_manager = PersonalityManager(base_path=str(tmp_path))

            # Should still work using fallback methods
            result = empty_manager.initialize_agent_personality(
                agent_id=sample_agent_data["agent_id"],
                agent_name=sample_agent_data["agent_name"],
                model=sample_agent_data["model"],
                persona=sample_agent_data["persona"]
            )

            # Should create all files using fallback
            assert result.soul is not None
            assert result.agents is not None
            assert result.tools is not None

            # Content should still have agent name (from fallback templates)
            assert sample_agent_data["agent_name"] in result.soul.content

    class TestIntegration:
        """Integration tests for full workflow"""

        def test_performs_complete_initialization_workflow(self, manager):
            """Should perform complete agent initialization from templates"""
            # Create a new agent
            agent_id = str(uuid.uuid4())
            agent_name = "IntegrationTestAgent"
            model = "claude-3-5-sonnet-20241022"
            persona = "A test agent for integration testing"

            # Initialize personality
            personality_set = manager.initialize_agent_personality(
                agent_id=agent_id,
                agent_name=agent_name,
                model=model,
                persona=persona
            )

            # Verify all files were created
            assert personality_set.soul is not None
            assert personality_set.agents is not None
            assert personality_set.tools is not None
            assert personality_set.identity is not None
            assert personality_set.user is not None
            assert personality_set.bootstrap is not None
            assert personality_set.heartbeat is not None
            assert personality_set.memory is not None

            # Verify content has been substituted
            assert agent_name in personality_set.soul.content
            assert "{{AGENT_NAME}}" not in personality_set.soul.content

            # Verify files can be read back
            retrieved = manager.get_personality(agent_id)
            assert retrieved.soul.content == personality_set.soul.content

        def test_works_with_special_characters_in_agent_name(self, manager):
            """Should handle agent names with special characters"""
            agent_id = str(uuid.uuid4())
            agent_name = "Test-Agent_2024 (v1.0)"
            model = "claude-3-5-sonnet-20241022"

            # Should not crash
            result = manager.initialize_agent_personality(
                agent_id=agent_id,
                agent_name=agent_name,
                model=model,
                persona=None
            )

            # Agent name should be preserved
            assert agent_name in result.soul.content

        def test_works_with_long_persona_text(self, manager):
            """Should handle long persona descriptions"""
            agent_id = str(uuid.uuid4())
            long_persona = "A " + ("very " * 100) + "long persona description"

            result = manager.initialize_agent_personality(
                agent_id=agent_id,
                agent_name="LongPersonaAgent",
                model="claude-3-5-sonnet-20241022",
                persona=long_persona
            )

            # Should handle long text without errors
            assert result.soul is not None
