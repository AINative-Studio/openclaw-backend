# Semantic Search Guide

## Overview

Semantic search enables natural language queries across conversation histories using vector embeddings. Unlike keyword search, semantic search understands meaning and context, finding relevant messages even when exact words don't match.

**Key Features:**
- Natural language queries (no need for exact keywords)
- Context-aware matching (understands synonyms and related concepts)
- Ranked results by relevance (similarity scores 0.0-1.0)
- Cross-conversation search capabilities
- Powered by ZeroDB Memory API with automatic embeddings

## How It Works

### 1. Message Storage with Embeddings

When a message is sent through the OpenClaw Bridge:

```python
# Step 1: Message sent to agent (via Gateway)
await bridge.send_message(session_key, "Can you explain async/await in Python?")

# Step 2: Bridge auto-persists to ConversationService
conversation_service.add_message(
    conversation_id=conversation.id,
    role="user",
    content="Can you explain async/await in Python?"
)

# Step 3: ConversationService stores in dual format
# 3a. ZeroDB Table (for pagination)
await zerodb.create_table_row(
    project_id=workspace.zerodb_project_id,
    table_name="messages",
    row_data={
        "conversation_id": str(conversation_id),
        "role": "user",
        "content": "Can you explain async/await in Python?",
        "timestamp": "2026-03-02T10:00:00Z"
    }
)

# 3b. ZeroDB Memory (for semantic search)
await zerodb.create_memory(
    title=f"Message in conversation {conversation_id}",
    content="Can you explain async/await in Python?",  # This gets embedded
    type="conversation",
    tags=[str(conversation_id), "user"],
    metadata={
        "conversation_id": str(conversation_id),
        "role": "user",
        "timestamp": "2026-03-02T10:00:00Z"
    }
)
# ZeroDB automatically creates vector embedding from content
```

**Vector Embedding Process:**

1. Message content converted to vector (array of ~1500 numbers)
2. Vector represents semantic meaning in high-dimensional space
3. Similar meanings have similar vectors (measured by cosine similarity)
4. Stored alongside message for fast retrieval

### 2. Search Query Processing

When you search a conversation:

```python
# User submits query
query = "Python async programming"

# Step 1: Search ZeroDB Memory API
search_results = await zerodb.search_memories(
    query=query,  # Query also converted to vector
    limit=10,     # Get top 10 most similar
    type="conversation"  # Only search conversation-type memories
)

# Step 2: Filter results to this conversation only
filtered_results = [
    result for result in search_results["results"]
    if result["metadata"]["conversation_id"] == str(conversation_id)
]

# Step 3: Return ranked results with scores
return {
    "results": filtered_results,
    "total": len(filtered_results),
    "query": query
}
```

**Similarity Matching:**

```
Query Vector:        [0.2, 0.8, 0.1, 0.5, ...]
Message 1 Vector:    [0.3, 0.7, 0.2, 0.4, ...]  → Similarity: 0.89 (high match)
Message 2 Vector:    [0.1, 0.2, 0.9, 0.1, ...]  → Similarity: 0.34 (low match)
```

Higher similarity score = more relevant result.

## Usage Examples

### Via API

#### Basic Search

```bash
curl -X POST "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I handle database errors?",
    "limit": 5
  }'
```

**Response:**

```json
{
  "results": {
    "results": [
      {
        "id": "mem_abc123",
        "content": "I'm getting a connection timeout when querying the database",
        "score": 0.87,
        "metadata": {
          "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
          "role": "user",
          "timestamp": "2026-03-02T09:30:00Z"
        }
      },
      {
        "id": "mem_def456",
        "content": "For database errors, wrap your queries in try/except blocks...",
        "score": 0.82,
        "metadata": {
          "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
          "role": "assistant",
          "timestamp": "2026-03-02T09:30:15Z"
        }
      }
    ],
    "total": 2,
    "query": "How do I handle database errors?"
  }
}
```

### Via ConversationService

#### Direct Service Call

```python
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID


async def search_example(db: AsyncSession, conversation_id: UUID):
    """Search conversation using ConversationService."""

    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)

        results = await service.search_conversation_semantic(
            conversation_id=conversation_id,
            query="Python error handling",
            limit=5
        )

        print(f"Found {results['total']} results")
        for result in results["results"]:
            print(f"Score: {result['score']:.2f}")
            print(f"Content: {result['content'][:100]}...")
            print(f"Role: {result['metadata']['role']}")
            print("---")
```

#### With Pagination Fallback

```python
async def search_with_fallback(db: AsyncSession, conversation_id: UUID, query: str):
    """
    Search with fallback to pagination if semantic search fails.

    Useful for handling graceful degradation when Memory API unavailable.
    """

    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)

        try:
            # Try semantic search first
            results = await service.search_conversation_semantic(
                conversation_id=conversation_id,
                query=query,
                limit=5
            )

            if results["total"] > 0:
                print("Using semantic search")
                return results["results"]
            else:
                print("No semantic results, falling back to recent messages")
                raise ValueError("No results")

        except Exception as e:
            print(f"Semantic search failed: {e}, using pagination fallback")

            # Fallback: Get recent messages
            messages = await service.get_messages(
                conversation_id=conversation_id,
                limit=20,
                offset=0
            )

            # Simple keyword filter
            query_lower = query.lower()
            filtered = [
                msg for msg in messages
                if query_lower in msg["content"].lower()
            ]

            return filtered
```

## Search Tips

### Query Formulation

#### Good Queries (Natural Language)

✓ **Descriptive questions:**
- "How do I configure authentication?"
- "What are the best practices for error handling?"
- "Explain the difference between sync and async code"

✓ **Conceptual searches:**
- "Database connection pooling strategies"
- "Security vulnerabilities in web applications"
- "Performance optimization techniques"

✓ **Problem descriptions:**
- "My API returns 500 errors intermittently"
- "Users can't log in after password reset"
- "Slow query performance on large datasets"

#### Poor Queries (Too Short/Generic)

✗ **Single words:**
- "error" (too generic, low semantic signal)
- "database" (matches too broadly)
- "python" (almost every message might match)

✗ **Keywords without context:**
- "api error 500" (prefer: "Why is my API returning 500 errors?")
- "login bug" (prefer: "Users unable to log in after password reset")

✗ **Code snippets alone:**
- "await db.execute(stmt)" (prefer: "How to execute async database queries?")

### Optimal Search Parameters

#### Limit Tuning

```python
# For quick context retrieval
results = await service.search_conversation_semantic(
    conversation_id=conv_id,
    query="authentication setup",
    limit=3  # Top 3 most relevant messages
)

# For comprehensive review
results = await service.search_conversation_semantic(
    conversation_id=conv_id,
    query="all error messages",
    limit=10  # Broader result set
)

# Don't exceed 20 - diminishing relevance
# Scores typically drop below 0.5 after top 10 results
```

#### Score Thresholds

```python
# Filter by score to remove low-relevance results
MIN_SCORE = 0.6  # Adjust based on your needs

results = await service.search_conversation_semantic(
    conversation_id=conv_id,
    query="database errors",
    limit=10
)

high_quality_results = [
    r for r in results["results"]
    if r["score"] >= MIN_SCORE
]

print(f"Found {len(high_quality_results)} high-quality matches")
```

**Score Guidelines:**

| Score Range | Interpretation | Action |
|-------------|----------------|--------|
| 0.8 - 1.0 | Excellent match | Definitely relevant |
| 0.6 - 0.8 | Good match | Likely relevant |
| 0.4 - 0.6 | Moderate match | May be relevant, review context |
| 0.0 - 0.4 | Weak match | Likely not relevant |

## Advanced Use Cases

### 1. Cross-Message Context Retrieval

Find all messages related to a specific topic:

```python
async def get_topic_context(
    db: AsyncSession,
    conversation_id: UUID,
    topic: str,
    min_score: float = 0.6
):
    """Retrieve all messages related to a topic."""

    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)

        results = await service.search_conversation_semantic(
            conversation_id=conversation_id,
            query=topic,
            limit=20
        )

        # Filter by score and sort by timestamp
        relevant_messages = [
            r for r in results["results"]
            if r["score"] >= min_score
        ]

        # Sort chronologically
        relevant_messages.sort(
            key=lambda x: x["metadata"]["timestamp"]
        )

        return relevant_messages


# Usage
context = await get_topic_context(
    db=db,
    conversation_id=conversation_id,
    topic="database schema changes",
    min_score=0.7
)

print(f"Found {len(context)} messages about database schema changes")
for msg in context:
    print(f"{msg['metadata']['timestamp']}: {msg['content'][:80]}...")
```

### 2. Question-Answer Pairing

Find assistant's answers to user questions:

```python
async def find_answer_to_question(
    db: AsyncSession,
    conversation_id: UUID,
    question: str
):
    """Find assistant's response to a specific question."""

    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)

        # Search for the question
        results = await service.search_conversation_semantic(
            conversation_id=conversation_id,
            query=question,
            limit=5
        )

        # Find user message with highest score
        user_message = None
        for result in results["results"]:
            if result["metadata"]["role"] == "user":
                user_message = result
                break

        if not user_message:
            return None

        # Get all messages (chronologically)
        all_messages = await service.get_messages(
            conversation_id=conversation_id,
            limit=200,
            offset=0
        )

        # Find the assistant's next message
        user_timestamp = user_message["metadata"]["timestamp"]
        for i, msg in enumerate(all_messages):
            if (msg["timestamp"] == user_timestamp and
                i + 1 < len(all_messages)):
                next_msg = all_messages[i + 1]
                if next_msg["role"] == "assistant":
                    return {
                        "question": user_message["content"],
                        "answer": next_msg["content"],
                        "timestamp": next_msg["timestamp"]
                    }

        return None


# Usage
qa = await find_answer_to_question(
    db=db,
    conversation_id=conversation_id,
    question="How do I configure async database connections?"
)

if qa:
    print(f"Q: {qa['question']}")
    print(f"A: {qa['answer']}")
```

### 3. Topic Clustering

Group related messages by semantic similarity:

```python
from collections import defaultdict


async def cluster_messages_by_topic(
    db: AsyncSession,
    conversation_id: UUID,
    topics: list[str]
):
    """Cluster messages into predefined topics."""

    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)

        clusters = defaultdict(list)

        for topic in topics:
            results = await service.search_conversation_semantic(
                conversation_id=conversation_id,
                query=topic,
                limit=10
            )

            for result in results["results"]:
                if result["score"] >= 0.6:
                    clusters[topic].append({
                        "content": result["content"],
                        "score": result["score"],
                        "timestamp": result["metadata"]["timestamp"]
                    })

        return dict(clusters)


# Usage
clusters = await cluster_messages_by_topic(
    db=db,
    conversation_id=conversation_id,
    topics=[
        "authentication",
        "database queries",
        "error handling",
        "performance optimization"
    ]
)

for topic, messages in clusters.items():
    print(f"\n{topic.upper()} ({len(messages)} messages):")
    for msg in messages[:3]:  # Top 3 per topic
        print(f"  [{msg['score']:.2f}] {msg['content'][:60]}...")
```

### 4. Temporal Search

Combine semantic search with time filtering:

```python
from datetime import datetime, timedelta


async def search_recent_on_topic(
    db: AsyncSession,
    conversation_id: UUID,
    topic: str,
    hours_ago: int = 24
):
    """Search for recent messages on a topic."""

    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)

        results = await service.search_conversation_semantic(
            conversation_id=conversation_id,
            query=topic,
            limit=20
        )

        # Filter by timestamp
        cutoff = datetime.now() - timedelta(hours=hours_ago)
        recent_results = [
            r for r in results["results"]
            if datetime.fromisoformat(r["metadata"]["timestamp"].replace("Z", "+00:00")) > cutoff
        ]

        return recent_results


# Usage
recent_errors = await search_recent_on_topic(
    db=db,
    conversation_id=conversation_id,
    topic="error messages",
    hours_ago=24
)

print(f"Found {len(recent_errors)} recent error discussions")
```

## Limitations and Considerations

### 1. Memory Storage Graceful Degradation

**Issue:** If Memory API fails during message storage, semantic search won't work for those messages.

**Symptom:** Search returns no results even though messages exist (visible via pagination).

**Check:**

```python
# Get message via pagination
messages = await service.get_messages(conversation_id, limit=50)
print(f"Messages in table: {len(messages)}")

# Try semantic search
results = await service.search_conversation_semantic(
    conversation_id,
    "any query",
    limit=50
)
print(f"Messages in memory: {results['total']}")

# If mismatch, some messages missing from Memory API
```

**Mitigation:** Use pagination fallback (see "Search with Fallback" example above).

### 2. Embedding Model Limitations

**Context Window:** ZeroDB embeddings have ~8000 token context window. Very long messages may be truncated.

**Recommendation:** Messages >2000 words should be split into smaller chunks.

### 3. Language Support

**Optimized For:** English language queries and messages

**Other Languages:** May work but with reduced accuracy. Consider language-specific prompts.

### 4. Real-Time Updates

**Indexing Delay:** New messages typically indexed within 1-2 seconds.

**Implication:** Brand-new messages might not appear in search immediately.

### 5. Score Calibration

**Variability:** Similarity scores depend on:
- Query phrasing
- Message length
- Domain specificity

**Best Practice:** Test score thresholds on your specific use case.

## Performance Optimization

### Caching Frequent Queries

```python
from functools import lru_cache
from datetime import datetime, timedelta


class SearchCache:
    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds

    def get(self, conversation_id: str, query: str):
        key = f"{conversation_id}:{query}"
        if key in self.cache:
            result, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return result
        return None

    def set(self, conversation_id: str, query: str, result):
        key = f"{conversation_id}:{query}"
        self.cache[key] = (result, datetime.now())


# Global cache instance
search_cache = SearchCache(ttl_seconds=300)


async def cached_search(
    db: AsyncSession,
    conversation_id: UUID,
    query: str,
    limit: int = 5
):
    """Search with caching for repeated queries."""

    # Check cache
    cached = search_cache.get(str(conversation_id), query)
    if cached:
        print("Cache hit")
        return cached

    # Not cached, perform search
    async with ZeroDBClient(api_key="your_api_key") as zerodb:
        service = ConversationService(db=db, zerodb_client=zerodb)
        results = await service.search_conversation_semantic(
            conversation_id=conversation_id,
            query=query,
            limit=limit
        )

    # Cache results
    search_cache.set(str(conversation_id), query, results)
    return results
```

### Batch Searches

```python
async def batch_search_multiple_conversations(
    db: AsyncSession,
    conversation_ids: list[UUID],
    query: str,
    limit: int = 5
):
    """Search multiple conversations in parallel."""

    import asyncio

    async def search_one(conv_id):
        async with ZeroDBClient(api_key="your_api_key") as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)
            return await service.search_conversation_semantic(
                conversation_id=conv_id,
                query=query,
                limit=limit
            )

    # Run searches concurrently
    tasks = [search_one(conv_id) for conv_id in conversation_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Combine and sort by score
    all_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Conversation {conversation_ids[i]} failed: {result}")
            continue

        for r in result["results"]:
            r["conversation_id"] = str(conversation_ids[i])
            all_results.append(r)

    # Sort by score (highest first)
    all_results.sort(key=lambda x: x["score"], reverse=True)

    return all_results[:limit]  # Top N across all conversations
```

## Troubleshooting

### No Results Returned

**Check 1:** Verify messages were stored in Memory API

```python
# Look for warning logs during message send
# "Memory storage failed - semantic search unavailable"
```

**Check 2:** Test with very generic query

```python
# Should match something
results = await service.search_conversation_semantic(
    conversation_id,
    "message",  # Generic term
    limit=10
)
```

**Check 3:** Verify ZeroDB Memory API is accessible

```bash
python scripts/test_zerodb_connection.py
# Check step 5 and 6 (Memory API tests)
```

### Low Relevance Scores

**Solution 1:** Rephrase query to be more specific

```python
# Instead of:
"errors"

# Try:
"database connection timeout errors"
```

**Solution 2:** Increase limit to see more results

```python
results = await service.search_conversation_semantic(
    conversation_id,
    query,
    limit=20  # See more to understand score distribution
)
```

### Unexpected Results

**Debug:** Print full results with scores

```python
results = await service.search_conversation_semantic(
    conversation_id,
    "your query",
    limit=10
)

for i, r in enumerate(results["results"]):
    print(f"\n{i+1}. Score: {r['score']:.3f}")
    print(f"   Role: {r['metadata']['role']}")
    print(f"   Content: {r['content']}")
```

## Next Steps

1. **Try basic searches:** Use simple queries to understand result quality
2. **Calibrate scores:** Find appropriate score thresholds for your use case
3. **Implement fallback:** Add pagination fallback for robustness
4. **Cache frequent queries:** Reduce API calls for common searches
5. **Monitor usage:** Track search performance and adjust limits

## Related Documentation

- [API Reference](chat-persistence-api.md) - Search endpoint details
- [Architecture](chat-persistence-architecture.md) - Dual storage design
- [Troubleshooting](chat-persistence-troubleshooting.md) - Common issues
