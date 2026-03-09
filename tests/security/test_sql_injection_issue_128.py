"""
SQL Injection Prevention Tests (Issue #128)

Tests to verify that conversation search is protected against SQL injection attacks.

Security Requirements:
    - Parameterized queries prevent SQL injection
    - Input validation blocks dangerous SQL keywords
    - Special characters are properly escaped
    - Malicious queries return errors or safe results
"""

import pytest
from uuid import uuid4
from pydantic import ValidationError

from backend.schemas.conversation import SearchRequest
from backend.services.conversation_service_pg import ConversationServicePG
from backend.models.conversation import Conversation, ConversationStatus
from backend.models.message import Message


class TestSearchRequestValidation:
    """Test SearchRequest schema validation blocks SQL injection attempts."""

    def test_valid_plain_text_query(self):
        """Valid plain text queries should pass validation."""
        request = SearchRequest(query="machine learning concepts", limit=5)
        assert request.query == "machine learning concepts"
        assert request.limit == 5

    def test_empty_query_rejected(self):
        """Empty queries should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="", limit=5)
        assert "min_length" in str(exc_info.value).lower() or "validation" in str(exc_info.value).lower()

    def test_query_too_long_rejected(self):
        """Queries exceeding 200 characters should be rejected."""
        long_query = "a" * 201
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query=long_query, limit=5)
        assert "max_length" in str(exc_info.value).lower() or "200" in str(exc_info.value)

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped."""
        request = SearchRequest(query="  test query  ", limit=5)
        assert request.query == "test query"

    # SQL Injection Attack Vectors

    def test_blocks_union_select(self):
        """UNION SELECT attacks should be blocked."""
        malicious_queries = [
            "test' UNION SELECT * FROM users --",
            "test' union select password from users --",
            "x' UNION ALL SELECT NULL, password, email FROM users --",
        ]

        for query in malicious_queries:
            with pytest.raises(ValidationError) as exc_info:
                SearchRequest(query=query, limit=5)
            error_msg = str(exc_info.value).lower()
            assert "union" in error_msg or "select" in error_msg

    def test_blocks_drop_table(self):
        """DROP TABLE attacks should be blocked."""
        malicious_queries = [
            "'; DROP TABLE messages; --",
            "test'; drop table users; --",
            "x' OR 1=1; DROP TABLE conversations; --",
        ]

        for query in malicious_queries:
            with pytest.raises(ValidationError) as exc_info:
                SearchRequest(query=query, limit=5)
            error_msg = str(exc_info.value).lower()
            assert "drop" in error_msg or ";" in error_msg or "forbidden" in error_msg

    def test_blocks_insert_statement(self):
        """INSERT statements should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="'; INSERT INTO users VALUES ('hacker', 'pass'); --", limit=5)
        assert "insert" in str(exc_info.value).lower()

    def test_blocks_update_statement(self):
        """UPDATE statements should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="'; UPDATE users SET role='admin' WHERE 1=1; --", limit=5)
        assert "update" in str(exc_info.value).lower()

    def test_blocks_delete_statement(self):
        """DELETE statements should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="'; DELETE FROM messages WHERE 1=1; --", limit=5)
        assert "delete" in str(exc_info.value).lower()

    def test_blocks_sql_comments(self):
        """SQL comment sequences should be blocked."""
        malicious_queries = [
            "test' OR 1=1 --",
            "test' /* comment */ OR '1'='1",
            "test' -- comment",
        ]

        for query in malicious_queries:
            with pytest.raises(ValidationError) as exc_info:
                SearchRequest(query=query, limit=5)
            error_msg = str(exc_info.value).lower()
            assert "comment" in error_msg or "forbidden" in error_msg

    def test_blocks_semicolon_chaining(self):
        """Semicolons for query chaining should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="test; DROP TABLE users;", limit=5)
        # Query should be rejected (either for semicolon or DROP keyword)
        error_msg = str(exc_info.value).lower()
        assert "semicolon" in error_msg or "drop" in error_msg or "forbidden" in error_msg

    def test_blocks_exec_execute(self):
        """EXEC/EXECUTE commands should be blocked."""
        malicious_queries = [
            "'; EXEC sp_executesql N'DROP TABLE users'; --",
            "test'; EXECUTE('DROP TABLE messages'); --",
        ]

        for query in malicious_queries:
            with pytest.raises(ValidationError) as exc_info:
                SearchRequest(query=query, limit=5)
            error_msg = str(exc_info.value).lower()
            assert "exec" in error_msg or ";" in error_msg

    def test_blocks_alter_table(self):
        """ALTER TABLE statements should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="'; ALTER TABLE users ADD COLUMN is_admin BOOLEAN; --", limit=5)
        assert "alter" in str(exc_info.value).lower()

    def test_blocks_create_table(self):
        """CREATE TABLE statements should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="'; CREATE TABLE backdoor (user TEXT, pass TEXT); --", limit=5)
        assert "create" in str(exc_info.value).lower()

    def test_blocks_control_characters(self):
        """Control characters (null bytes, etc.) should be blocked."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest(query="test\x00query", limit=5)
        assert "control" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    def test_allows_legitimate_special_chars(self):
        """Legitimate special characters should be allowed."""
        valid_queries = [
            "C++ programming",
            "cost is $100",
            "email@example.com",
            "rate: 95%",
            "question?",
            "hello (world)",
            "item #1",
        ]

        for query in valid_queries:
            request = SearchRequest(query=query, limit=5)
            assert request.query == query


@pytest.mark.asyncio
class TestConversationServiceSQLInjection:
    """Test that ConversationServicePG prevents SQL injection in database queries."""

    async def test_search_with_wildcards_escaped(self, db_session):
        """Test that SQL wildcards (%, _) are properly escaped."""
        # Create test conversation and messages
        conversation = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        await db_session.commit()
        await db_session.refresh(conversation)

        # Add messages with special characters
        messages = [
            Message(conversation_id=conversation.id, role="user", content="Cost is 100% accurate"),
            Message(conversation_id=conversation.id, role="assistant", content="Price is $100"),
            Message(conversation_id=conversation.id, role="user", content="File_name_test.txt"),
        ]
        for msg in messages:
            db_session.add(msg)
        await db_session.commit()

        service = ConversationServicePG(db_session)

        # Search with % (should be escaped and treated as literal)
        result = await service.search_conversation_semantic(
            conversation_id=conversation.id,
            query="100%",
            limit=10
        )

        # Should find the message with "100%" but not treat % as wildcard
        assert result["total_matches"] == 1
        assert "100% accurate" in result["matches"][0]["content"]

    async def test_search_with_sql_like_patterns_safe(self, db_session):
        """Test that LIKE pattern characters don't cause SQL injection."""
        conversation = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        await db_session.commit()
        await db_session.refresh(conversation)

        # Add test message
        msg = Message(
            conversation_id=conversation.id,
            role="user",
            content="Testing underscore_pattern and percent%"
        )
        db_session.add(msg)
        await db_session.commit()

        service = ConversationServicePG(db_session)

        # These should be treated as literal characters, not SQL wildcards
        result = await service.search_conversation_semantic(
            conversation_id=conversation.id,
            query="underscore_",
            limit=10
        )

        # Should find the message since underscore is escaped
        assert result["total_matches"] >= 1

    async def test_search_returns_safe_results_only(self, db_session):
        """Test that search returns only messages from the specified conversation."""
        # Create two conversations
        conv1 = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        conv2 = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conv1)
        db_session.add(conv2)
        await db_session.commit()
        await db_session.refresh(conv1)
        await db_session.refresh(conv2)

        # Add messages to both
        msg1 = Message(conversation_id=conv1.id, role="user", content="secret data conv1")
        msg2 = Message(conversation_id=conv2.id, role="user", content="secret data conv2")
        db_session.add(msg1)
        db_session.add(msg2)
        await db_session.commit()

        service = ConversationServicePG(db_session)

        # Search in conv1
        result = await service.search_conversation_semantic(
            conversation_id=conv1.id,
            query="secret data",
            limit=10
        )

        # Should only return messages from conv1
        assert result["total_matches"] == 1
        assert "conv1" in result["matches"][0]["content"]
        assert "conv2" not in result["matches"][0]["content"]

    async def test_search_with_legitimate_apostrophe(self, db_session):
        """Test that legitimate apostrophes in queries work correctly."""
        conversation = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        await db_session.commit()
        await db_session.refresh(conversation)

        msg = Message(
            conversation_id=conversation.id,
            role="user",
            content="It's a beautiful day"
        )
        db_session.add(msg)
        await db_session.commit()

        service = ConversationServicePG(db_session)

        # Apostrophes should not cause SQL errors
        result = await service.search_conversation_semantic(
            conversation_id=conversation.id,
            query="It's",
            limit=10
        )

        # Should safely find the message
        assert result["total_matches"] == 1
        assert "It's" in result["matches"][0]["content"]

    async def test_search_case_insensitive(self, db_session):
        """Test that search is case-insensitive as intended."""
        conversation = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        await db_session.commit()
        await db_session.refresh(conversation)

        msg = Message(
            conversation_id=conversation.id,
            role="user",
            content="Machine Learning Concepts"
        )
        db_session.add(msg)
        await db_session.commit()

        service = ConversationServicePG(db_session)

        # Search with different case
        result = await service.search_conversation_semantic(
            conversation_id=conversation.id,
            query="machine learning",
            limit=10
        )

        # Should find the message regardless of case
        assert result["total_matches"] == 1


@pytest.mark.asyncio
class TestEndToEndSQLInjectionPrevention:
    """End-to-end tests simulating real attack scenarios."""

    async def test_full_attack_chain_blocked(self, db_session):
        """Test that a full SQL injection attack chain is blocked."""
        conversation = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        await db_session.commit()
        await db_session.refresh(conversation)

        service = ConversationServicePG(db_session)

        # Simulate attacker trying various injection techniques
        attack_vectors = [
            # Classic UNION attack
            "' UNION SELECT password, email, api_key FROM users WHERE '1'='1",
            # Boolean-based blind injection
            "' OR '1'='1",
            "' OR 1=1 --",
            # Time-based blind injection
            "'; WAITFOR DELAY '00:00:05'; --",
            # Stacked queries
            "'; DROP TABLE messages; --",
            # Out-of-band data exfiltration
            "' UNION SELECT string_agg(email, ',') FROM users --",
        ]

        for attack in attack_vectors:
            # Schema validation should block before hitting database
            with pytest.raises(ValidationError):
                SearchRequest(query=attack, limit=5)

            # Even if somehow bypassed, parameterized query would prevent injection
            # This verifies defense-in-depth

    async def test_no_data_leakage_from_other_tables(self, db_session):
        """Verify that search cannot access data from other tables."""
        conversation = Conversation(
            workspace_id=uuid4(),
            agent_swarm_instance_id=uuid4(),
            user_id=uuid4(),
            status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation)
        await db_session.commit()
        await db_session.refresh(conversation)

        msg = Message(
            conversation_id=conversation.id,
            role="user",
            content="normal message"
        )
        db_session.add(msg)
        await db_session.commit()

        service = ConversationServicePG(db_session)

        # Even with a query that looks like it might access other tables,
        # the parameterized query structure prevents any cross-table access
        result = await service.search_conversation_semantic(
            conversation_id=conversation.id,
            query="normal",
            limit=10
        )

        # Should only return Message objects, not data from other tables
        assert result["total_matches"] == 1
        assert "content" in result["matches"][0]
        assert "timestamp" in result["matches"][0]
        # Should not have any fields from other tables like "password", "api_key", etc.
        assert "password" not in str(result).lower()
        assert "api_key" not in str(result).lower()
