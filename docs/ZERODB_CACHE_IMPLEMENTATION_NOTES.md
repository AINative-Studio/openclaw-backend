# ZeroDB Cache Service Implementation Notes (Issue #123)

## Status: PARTIAL IMPLEMENTATION

**Implementation Date:** March 9, 2026
**Developer:** Claude Code Agent
**Issue:** #123 - Implement ZeroDB Cache Service with Auto-Cleanup

## Summary

Implemented a serverless caching layer using ZeroDB NoSQL tables to replace Redis infrastructure. **Discovered significant API limitations** that require design changes.

## What Was Completed

### 1. ZeroDB Client MongoDB-Style Query Methods ✅
- **File:** `backend/integrations/zerodb_client.py`
- **Added Methods:**
  - `query_rows(table_name, filter_query, project_id, limit, skip)` - MongoDB-style queries
  - `insert_rows(table_name, rows, project_id)` - Bulk row insertion
  - `update_rows()` - **INCOMPLETE** - API doesn't support single-row updates
  - `delete_rows()` - **INCOMPLETE** - API doesn't support single-row deletes

### 2. ZeroDBCacheService Implementation ✅ (with limitations)
- **File:** `backend/services/zerodb_cache_service.py`
- **Implemented Methods:**
  - `set(key, value, ttl)` - **BLOCKED** - needs UPDATE API
  - `get(key)` - ✅ Works (uses query)
  - `delete(key)` - **BLOCKED** - needs DELETE API
  - `exists(key)` - ✅ Works (uses query)
  - `increment(counter_key)` - **BLOCKED** - needs UPDATE API
  - `cleanup_expired()` - **BLOCKED** - needs DELETE API
  - `get_stats()` - ✅ Partially works (read-only stats)

### 3. Test Suite ✅
- **File:** `tests/services/test_zerodb_cache_service.py`
- Created 7 comprehensive TDD tests
- Tests currently FAIL due to API limitations (expected - RED state)

### 4. Infrastructure Setup ✅
- Created ZeroDB table `openclaw_cache` in project `883db50b-1857-4cd8-8de3-088ab589e65e`
- Added `ZERODB_PROJECT_ID` to `.env`
- Setup script: `scripts/setup_zerodb_cache_table.py`

## Critical API Limitations Discovered

### ZeroDB API Does NOT Support:

1. **Single-row UPDATE operations**
   - No `PATCH /tables/{table_name}/rows/{row_id}` endpoint
   - Only bulk update via batch operations API

2. **Single-row DELETE operations**
   - No `DELETE /tables/{table_name}/rows/{row_id}` endpoint
   - Only bulk delete via batch operations API

3. **Upsert (INSERT OR UPDATE) semantics**
   - Cannot atomically check-and-update a row
   - Must use query → delete → insert pattern (race condition prone)

### What The API DOES Support:

✅ **Query** - MongoDB-style filtering via POST `/query`
✅ **Insert** - Single row via POST `/rows` with `{"row_data": {...}}`
❌ **Update** - Only via batch operations API (not yet implemented)
❌ **Delete** - Only via batch operations API (not yet implemented)

### API Response Format:

```python
# Query Response
{
    "total": 1,
    "data": [{
        "row_id": "uuid",
        "row_data": {"key": "value", ...},  # Actual data here
        "created_at": "timestamp",
        "updated_at": "timestamp"
    }]
}

# Insert Request
{"row_data": {"key": "test", "value": "data"}}

# Insert Response
{
    "row_id": "uuid",
    "row_data": {...},
    "created_at": "timestamp"
}
```

## Recommended Next Steps

### Option 1: Implement Batch Operations API (Recommended)

The ZeroDB API supports batch operations at:
- `POST /v1/public/{project_id}/database/batch-operations`

This endpoint supports:
- Multiple queries
- Multiple inserts
- **Multiple updates** (with MongoDB-style filters)
- **Multiple deletes** (with MongoDB-style filters)

**Implementation:**
1. Add `batch_operations(operations)` method to ZeroDBClient
2. Refactor `update_rows()` and `delete_rows()` to use batch API
3. Implement cache operations as single-operation batches

**Pros:**
- Uses official API correctly
- Supports all cache operations
- Future-proof for actual batch use cases

**Cons:**
- More complex client implementation
- Batch overhead for single operations

### Option 2: Query-Delete-Insert Pattern (Workaround)

Implement upsert as:
1. Query for existing row
2. If exists: Delete it
3. Insert new row

**Pros:**
- Simple implementation
- Uses only working APIs

**Cons:**
- **Race conditions** (not atomic)
- Multiple API calls per operation
- Poor performance

### Option 3: Use Different Storage Backend

Consider alternatives:
- PostgreSQL (via ZeroDB's dedicated PostgreSQL instances)
- Redis (managed service)
- DynamoDB/Firebase (if AWS/GCP available)

**Pros:**
- Proven cache semantics
- Better performance
- No API limitations

**Cons:**
- Additional infrastructure
- Defeats "serverless" goal

## Test Results

```bash
$ python3 -m pytest tests/services/test_zerodb_cache_service.py -v

7 tests FAILED:
- test_set_and_get_value: 404 on update_rows
- test_get_expired_value_returns_none: 404 on update_rows
- test_delete_key: 404 on update_rows
- test_exists_check: 404 on update_rows (for initial exists check)
- test_cleanup_expired_entries: 404 on update_rows
- test_increment_counter: 404 on delete_rows
- test_get_stats: 404 on update_rows
```

## Files Modified

```
backend/integrations/zerodb_client.py          # Extended with query/insert methods
backend/services/zerodb_cache_service.py        # Cache service (incomplete)
tests/services/test_zerodb_cache_service.py     # 7 TDD tests
scripts/setup_zerodb_cache_table.py             # Table setup script
docs/ZERODB_CACHE_IMPLEMENTATION_NOTES.md       # This file
.env                                            # Added ZERODB_PROJECT_ID
```

## Conclusion

**Issue #123 is BLOCKED** pending decision on batch operations API implementation. The groundwork is complete:
- Client infrastructure ✅
- Service architecture ✅
- Test suite ✅
- Table provisioned ✅

**Decision Required:** Choose Option 1, 2, or 3 above before proceeding.

**Recommended:** **Option 1 (Batch Operations API)** - Implement full batch operations support in ZeroDBClient to unlock UPDATE/DELETE functionality.

---

**Next Developer:** Start with implementing `batch_operations()` method in ZeroDBClient based on ZeroDB API documentation for batch operations endpoint.
