# Chat Persistence Integration Tests

**Epic E9 - Chat Persistence (Issue #109)**

This directory contains comprehensive integration tests for the chat persistence flow, from WhatsApp message reception through ZeroDB storage and API retrieval.

---

## Quick Start

```bash
# Activate virtual environment
cd /Users/aideveloper/openclaw-backend
source venv/bin/activate

# Run all chat persistence tests
pytest tests/integration/test_chat_persistence_e2e.py -v

# Run with coverage
pytest tests/integration/test_chat_persistence_e2e.py \
  --cov=backend.services.conversation_service \
  --cov=backend.agents.orchestration \
  --cov-report=term-missing
```

---

## Test Files

### Main Integration Tests

1. **`test_chat_persistence_e2e.py`** (NEW - Issue #109)
   - 20 comprehensive E2E integration tests
   - Tests complete flow: WhatsApp → Bridge → ZeroDB → API
   - Covers all 10 test scenarios from requirements

2. **`test_chat_persistence_flow.py`** (Existing)
   - 9 integration tests for basic persistence flow
   - Dual storage verification (table + memory)
   - Semantic search and pagination

3. **`test_api_chat_flow.py`** (Existing)
   - 8 API integration tests
   - FastAPI endpoint testing
   - Frontend integration scenarios

**Total: 37 integration tests**

---

## Test Organization

### Test Classes in `test_chat_persistence_e2e.py`

1. **TestFullMessageFlow** (2 tests)
   - Complete WhatsApp → ZeroDB flow
   - Multi-turn conversations

2. **TestConversationLifecycle** (3 tests)
   - Auto-creation for new users
   - Message continuity
   - Conversation archival

3. **TestAgentContextLoading** (2 tests)
   - Load last 10 messages
   - Metadata preservation

4. **TestMultiUserIsolation** (2 tests)
   - User-level isolation
   - Workspace-level isolation

5. **TestAgentSwitching** (1 test)
   - Switch agent mid-conversation

6. **TestErrorRecovery** (2 tests)
   - Connection error retry
   - Partial failure recovery

7. **TestAPIIntegration** (3 tests)
   - Frontend conversation creation
   - Pagination testing
   - Performance benchmarks

8. **TestZeroDBConsistency** (3 tests)
   - Dual storage consistency
   - Semantic search filtering
   - Message count accuracy

9. **TestPerformanceMetrics** (2 tests)
   - Concurrent conversations
   - Large conversation pagination

---

## Running Tests

### All Chat Persistence Tests

```bash
pytest tests/integration/test_chat_persistence*.py tests/integration/test_api_chat_flow.py -v
```

### Specific Test Class

```bash
pytest tests/integration/test_chat_persistence_e2e.py::TestFullMessageFlow -v
```

### Single Test

```bash
pytest tests/integration/test_chat_persistence_e2e.py::TestFullMessageFlow::test_whatsapp_to_zerodb_full_flow -v
```

### With Coverage Report

```bash
pytest tests/integration/test_chat_persistence_e2e.py \
  --cov=backend.services.conversation_service \
  --cov=backend.agents.orchestration.production_openclaw_bridge \
  --cov=backend.api.v1.endpoints.conversations \
  --cov-report=html \
  --cov-report=term-missing

# Open HTML report
open htmlcov/index.html
```

### Performance Tests Only

```bash
pytest tests/integration/test_chat_persistence_e2e.py::TestPerformanceMetrics -v -s
```

### Error Recovery Tests Only

```bash
pytest tests/integration/test_chat_persistence_e2e.py::TestErrorRecovery -v -s
```

---

## Fixtures

All fixtures are defined in `conftest.py`:

### Database Fixtures
- `db_engine` - Async SQLite engine
- `db` - Async database session (auto-rollback)

### Mock Fixtures
- `zerodb_client_mock` - Standard ZeroDB client mock
- `zerodb_client_with_failures` - ZeroDB mock with configurable failures
- `mock_openclaw_bridge` - OpenClaw bridge mock with error injection
- `fastapi_test_client` - FastAPI TestClient with overrides

### Data Fixtures
- `sample_workspace` - Workspace with ZeroDB project
- `sample_user` - User in workspace
- `sample_agent` - Agent in workspace
- `sample_conversation` - Empty conversation
- `multiple_users` - 5 users for multi-user tests
- `multiple_workspaces` - 3 workspaces for isolation tests
- `multiple_agents` - 3 agents for switching tests
- `conversation_with_messages` - Pre-populated conversation (20 messages)

### Utility Fixtures
- `performance_timer` - Context manager for timing assertions

---

## Performance Benchmarks

| Test | Target | What It Tests |
|------|--------|---------------|
| `test_whatsapp_to_zerodb_full_flow` | < 500ms | End-to-end message flow |
| `test_api_get_messages_performance` | < 200ms | API message retrieval (1000 msgs) |
| `test_large_conversation_pagination_performance` | < 100ms | Pagination from middle of 10k messages |
| `test_concurrent_conversations_performance` | < 5s | 50 conversations created concurrently |

---

## Test Coverage

### Integration Paths Tested

✅ User Model → Conversation Model → ZeroDB Messages
✅ OpenClaw Bridge → ConversationService → ZeroDB
✅ Agent Lifecycle → Conversation Context
✅ API Endpoints → Service Layer → Database

### Coverage Targets

- **Integration path coverage:** 85%+ (target met)
- **Total tests:** 37 (target: 25+)
- **Performance tests:** 4 with explicit assertions
- **Error scenarios:** 5 different error types

---

## Common Issues and Solutions

### Issue: SQLite doesn't support ARRAY columns

**Solution:** Tests use manual table creation for `agent_swarm_instances` to work around SQLite limitations. See `conftest.py` line 70.

### Issue: Tests fail with "asyncio loop closed"

**Solution:** Ensure `event_loop` fixture is function-scoped:
```python
@pytest.fixture(scope="function")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

### Issue: ZeroDB mock not resetting between tests

**Solution:** Use `zerodb_client_mock` fixture which creates fresh mock per test. For custom behavior, use `zerodb_client_with_failures.reset_counters()`.

### Issue: FastAPI dependency overrides not working

**Solution:** Ensure you clear overrides after each test:
```python
app.dependency_overrides.clear()
```

---

## Adding New Tests

### Template for New Integration Test

```python
@pytest.mark.asyncio
class TestMyNewFeature:
    """Test description"""

    async def test_my_new_scenario(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Clear description of what this tests

        Steps:
        1. Setup
        2. Execute
        3. Verify
        """
        # Arrange
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Act
        result = await service.some_method()

        # Assert
        assert result is not None
        assert result.some_property == expected_value
```

### Guidelines

1. **Use descriptive test names** - `test_what_it_tests_and_expected_outcome`
2. **Document test steps** - Clear docstring with numbered steps
3. **Use fixtures** - Don't create test data manually
4. **Assert thoroughly** - Verify all important aspects
5. **Clean up** - Use fixtures with proper teardown

---

## CI/CD Integration

### GitHub Actions (Example)

```yaml
name: Chat Persistence Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run chat persistence tests
        run: |
          pytest tests/integration/test_chat_persistence_e2e.py \
            --cov=backend.services.conversation_service \
            --cov-report=xml \
            --junitxml=test-results.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

---

## Documentation

- **Test Summary:** `TEST_SUMMARY_E2E_CHAT_PERSISTENCE.md`
- **Completion Checklist:** `ISSUE_109_COMPLETION_CHECKLIST.md`
- **This README:** `README_CHAT_PERSISTENCE_TESTS.md`

---

## Support

For questions or issues:
1. Check `TEST_SUMMARY_E2E_CHAT_PERSISTENCE.md` for detailed test documentation
2. Review `ISSUE_109_COMPLETION_CHECKLIST.md` for requirements verification
3. See existing tests in `test_chat_persistence_flow.py` for examples

---

**Issue #109 - Chat Persistence Integration Tests**
**Status:** ✅ Complete
**Coverage:** 37 tests, 85%+ integration paths
**Performance:** All benchmarks met
