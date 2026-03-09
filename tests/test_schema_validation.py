"""
Integration tests for Schema Input Validation (Issue #131)

Tests that Pydantic schemas properly validate and sanitize inputs:
    - ConversationCreate / AddMessageRequest
    - CreateSwarmRequest / UpdateSwarmRequest
    - CreateTemplateRequest / UpdateTemplateRequest
    - ZaloOAuthRequest / ZaloMessageRequest
"""

import pytest
from pydantic import ValidationError
from uuid import uuid4

from backend.schemas.conversation import (
    AddMessageRequest,
    ConversationResponse,
    SearchRequest,
)
from backend.schemas.agent_swarm import (
    CreateSwarmRequest,
    UpdateSwarmRequest,
    AddAgentsRequest,
)
from backend.schemas.agent_template import (
    CreateTemplateRequest,
    UpdateTemplateRequest,
)
from backend.schemas.zalo_schemas import (
    ZaloOAuthRequest,
    ZaloMessageRequest,
)


class TestConversationSchemas:
    """Test conversation schema validation."""

    def test_add_message_sanitizes_html(self):
        """Message content should have HTML/XSS removed."""
        request = AddMessageRequest(
            role="user",
            content="Hello <script>alert('XSS')</script>world",
            metadata={}
        )
        # Script tags should be removed
        assert "<script>" not in request.content
        assert "alert" in request.content  # Text content preserved
        assert "world" in request.content

    def test_add_message_enforces_role_enum(self):
        """Message role should be restricted to valid values."""
        # Valid roles
        for role in ["user", "assistant", "system"]:
            request = AddMessageRequest(role=role, content="Test")
            assert request.role == role

        # Invalid role
        with pytest.raises(ValidationError):
            AddMessageRequest(role="hacker", content="Test")

    def test_add_message_validates_metadata_depth(self):
        """Message metadata should have depth limits."""
        # Valid metadata (depth 2)
        valid_metadata = {
            "source": "whatsapp",
            "user": {"id": "123", "name": "Alice"}
        }
        request = AddMessageRequest(role="user", content="Test", metadata=valid_metadata)
        assert request.metadata == valid_metadata

        # Invalid metadata (depth 4 - exceeds limit of 3)
        deep_metadata = {
            "a": {"b": {"c": {"d": "too deep"}}}
        }
        with pytest.raises(ValidationError, match="maximum nesting depth"):
            AddMessageRequest(role="user", content="Test", metadata=deep_metadata)

    def test_add_message_blocks_dangerous_metadata_keys(self):
        """Dangerous keys in metadata should be blocked."""
        with pytest.raises(ValidationError, match="dangerous key"):
            AddMessageRequest(
                role="user",
                content="Test",
                metadata={"__proto__": "polluted"}
            )

    def test_add_message_max_length(self):
        """Message content should have length limits."""
        # Max 50,000 characters
        valid_content = "a" * 50000
        request = AddMessageRequest(role="user", content=valid_content)
        assert len(request.content) == 50000

        # Exceeds limit
        with pytest.raises(ValidationError):
            AddMessageRequest(role="user", content="a" * 50001)

    def test_search_request_blocks_sql_injection(self):
        """Search query should block SQL keywords."""
        # Valid search query
        request = SearchRequest(query="machine learning", limit=5)
        assert request.query == "machine learning"

        # SQL injection attempt
        with pytest.raises(ValidationError, match="forbidden SQL keyword"):
            SearchRequest(query="'; DROP TABLE users--")

    def test_conversation_response_enforces_channel_enum(self):
        """Channel should be restricted to known types."""
        # Valid channel
        response = ConversationResponse(
            id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            channel="whatsapp",
            channel_conversation_id="123",
            status="ACTIVE",
            created_at="2024-01-01T00:00:00Z"
        )
        assert response.channel == "whatsapp"

        # Invalid channel
        with pytest.raises(ValidationError):
            ConversationResponse(
                id=uuid4(),
                workspace_id=uuid4(),
                user_id=uuid4(),
                channel="malicious_channel",
                channel_conversation_id="123",
                status="ACTIVE",
                created_at="2024-01-01T00:00:00Z"
            )


class TestAgentSwarmSchemas:
    """Test agent swarm schema validation."""

    def test_create_swarm_sanitizes_html(self):
        """Swarm name/description should have HTML removed."""
        request = CreateSwarmRequest(
            name="Test <b>Swarm</b>",
            description="Description with <script>alert(1)</script>",
            strategy="sequential"
        )
        assert "<b>" not in request.name
        assert "<script>" not in request.description

    def test_create_swarm_enforces_strategy_enum(self):
        """Strategy should be restricted to valid values."""
        # Valid strategies
        for strategy in ["sequential", "parallel", "hierarchical", "democratic", "custom"]:
            request = CreateSwarmRequest(name="Test", strategy=strategy)
            assert request.strategy == strategy

        # Invalid strategy
        with pytest.raises(ValidationError):
            CreateSwarmRequest(name="Test", strategy="invalid_strategy")

    def test_create_swarm_validates_agent_ids(self):
        """Agent IDs should be alphanumeric with dashes/underscores."""
        # Valid agent IDs
        request = CreateSwarmRequest(
            name="Test",
            strategy="sequential",
            agent_ids=["agent-1", "agent_2", "agent3"]
        )
        assert len(request.agent_ids) == 3

        # Invalid agent ID (contains @)
        with pytest.raises(ValidationError, match="invalid characters"):
            CreateSwarmRequest(
                name="Test",
                strategy="sequential",
                agent_ids=["agent@malicious"]
            )

    def test_create_swarm_validates_configuration_structure(self):
        """Configuration should have depth/key limits."""
        # Valid configuration
        valid_config = {
            "timeout": 300,
            "retry": {"max_attempts": 3, "backoff": "exponential"}
        }
        request = CreateSwarmRequest(
            name="Test",
            strategy="sequential",
            configuration=valid_config
        )
        assert request.configuration == valid_config

        # Too many keys (>100)
        large_config = {f"key_{i}": i for i in range(101)}
        with pytest.raises(ValidationError):  # Error message varies
            CreateSwarmRequest(
                name="Test",
                strategy="sequential",
                configuration=large_config
            )

    def test_add_agents_validates_ids(self):
        """Agent IDs in add/remove requests should be validated."""
        # Valid
        request = AddAgentsRequest(agent_ids=["agent-1", "agent-2"])
        assert len(request.agent_ids) == 2

        # Invalid
        with pytest.raises(ValidationError, match="invalid characters"):
            AddAgentsRequest(agent_ids=["agent@bad"])

    def test_swarm_max_agent_list_size(self):
        """Agent ID lists should have size limits."""
        # Max 100 agents
        valid_ids = [f"agent-{i}" for i in range(100)]
        request = CreateSwarmRequest(
            name="Test",
            strategy="sequential",
            agent_ids=valid_ids
        )
        assert len(request.agent_ids) == 100

        # Exceeds limit
        with pytest.raises(ValidationError):
            CreateSwarmRequest(
                name="Test",
                strategy="sequential",
                agent_ids=[f"agent-{i}" for i in range(101)]
            )


class TestAgentTemplateSchemas:
    """Test agent template schema validation."""

    def test_create_template_sanitizes_html(self):
        """Template text fields should have HTML removed."""
        request = CreateTemplateRequest(
            name="Template <script>alert(1)</script>",
            category="backend",
            default_persona="Persona with <b>formatting</b>"
        )
        assert "<script>" not in request.name
        assert "<b>" not in request.default_persona

    def test_create_template_validates_icon_names(self):
        """Icon names should be alphanumeric with dashes/underscores."""
        # Valid icons
        request = CreateTemplateRequest(
            name="Test",
            category="backend",
            icons=["code-icon", "api_icon", "database"]
        )
        assert len(request.icons) == 3

        # Invalid icon (contains spaces)
        with pytest.raises(ValidationError, match="invalid characters"):
            CreateTemplateRequest(
                name="Test",
                category="backend",
                icons=["invalid icon name"]
            )

    def test_create_template_validates_heartbeat_interval(self):
        """Heartbeat interval should match format: <number><unit>."""
        # Valid formats
        for interval in ["5m", "1h", "30s", "1d"]:
            request = CreateTemplateRequest(
                name="Test",
                category="backend",
                default_heartbeat_interval=interval
            )
            assert request.default_heartbeat_interval == interval

        # Invalid format
        with pytest.raises(ValidationError, match="Invalid heartbeat interval"):
            CreateTemplateRequest(
                name="Test",
                category="backend",
                default_heartbeat_interval="5 minutes"
            )

    def test_create_template_sanitizes_checklist(self):
        """Checklist items should be sanitized."""
        request = CreateTemplateRequest(
            name="Test",
            category="backend",
            default_checklist=[
                "Step 1 <script>alert(1)</script>",
                "Step 2 with <b>HTML</b>"
            ]
        )
        assert all("<" not in item for item in request.default_checklist)

    def test_create_template_max_icon_count(self):
        """Icon list should have size limit."""
        # Max 10 icons
        valid_icons = [f"icon-{i}" for i in range(10)]
        request = CreateTemplateRequest(
            name="Test",
            category="backend",
            icons=valid_icons
        )
        assert len(request.icons) == 10

        # Exceeds limit
        with pytest.raises(ValidationError):
            CreateTemplateRequest(
                name="Test",
                category="backend",
                icons=[f"icon-{i}" for i in range(11)]
            )


class TestZaloSchemas:
    """Test Zalo schema validation."""

    def test_oauth_request_validates_redirect_uri(self):
        """Redirect URI should be a valid URL."""
        # Valid HTTPS URL
        request = ZaloOAuthRequest(redirect_uri="https://example.com/callback")
        assert request.redirect_uri == "https://example.com/callback"

        # Invalid URL (no protocol)
        with pytest.raises(ValidationError, match="must include protocol"):
            ZaloOAuthRequest(redirect_uri="example.com/callback")

        # Dangerous protocol
        with pytest.raises(ValidationError, match="protocol not allowed"):
            ZaloOAuthRequest(redirect_uri="javascript:alert(1)")

    def test_message_request_sanitizes_html(self):
        """Message text should be sanitized."""
        request = ZaloMessageRequest(
            workspace_id=uuid4(),
            user_id="zalo_user_123",
            message="Hello <script>alert(1)</script>world"
        )
        assert "<script>" not in request.message
        assert "Hello" in request.message
        assert "world" in request.message

    def test_message_request_max_length(self):
        """Message should have length limit."""
        # Max 5000 characters
        valid_message = "a" * 5000
        request = ZaloMessageRequest(
            workspace_id=uuid4(),
            user_id="zalo_user_123",
            message=valid_message
        )
        assert len(request.message) == 5000

        # Exceeds limit
        with pytest.raises(ValidationError):
            ZaloMessageRequest(
                workspace_id=uuid4(),
                user_id="zalo_user_123",
                message="a" * 5001
            )

    def test_message_request_empty_message_rejected(self):
        """Empty messages should be rejected."""
        # Pydantic enforces min_length=1, which gives "String should have at least 1 character"
        with pytest.raises(ValidationError):
            ZaloMessageRequest(
                workspace_id=uuid4(),
                user_id="zalo_user_123",
                message=""
            )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_unicode_characters_preserved(self):
        """Unicode characters should be preserved."""
        request = AddMessageRequest(
            role="user",
            content="Hello 世界 🌍",
            metadata={}
        )
        assert "世界" in request.content
        assert "🌍" in request.content

    def test_nested_xss_attempts(self):
        """Nested XSS attempts should be sanitized."""
        request = AddMessageRequest(
            role="user",
            content="<<script>alert(1)</script>script>alert(2)<</script>/script>",
            metadata={}
        )
        # All script tags should be removed
        assert "<script>" not in request.content.lower()

    def test_case_sensitivity_in_validation(self):
        """Validation should be case-insensitive where appropriate."""
        # SQL keywords are case-insensitive
        with pytest.raises(ValidationError, match="SELECT"):
            SearchRequest(query="SeLeCt * FrOm users")

    def test_whitespace_handling(self):
        """Whitespace should be handled correctly."""
        # Leading/trailing whitespace stripped
        request = AddMessageRequest(
            role="user",
            content="   Hello world   ",
            metadata={}
        )
        # Content should be trimmed (by sanitize_html)
        assert request.content == "Hello world"

    def test_metadata_with_empty_values(self):
        """Metadata with empty values should be allowed."""
        request = AddMessageRequest(
            role="user",
            content="Test",
            metadata={"key": "", "count": 0, "flag": False}
        )
        assert request.metadata["key"] == ""
        assert request.metadata["count"] == 0
        assert request.metadata["flag"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
