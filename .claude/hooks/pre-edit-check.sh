#!/bin/bash
# .claude/hooks/pre-edit-check.sh
# PreToolUse hook: Enforces documentation-first requirement for high-risk file changes
# Blocks Edit/Write operations on frontend, backend API, and database files
# until agent confirms documentation has been reviewed

set -e

# Read event JSON from stdin
EVENT_JSON=$(cat)

# Extract file_path from tool_input using jq
FILE_PATH=$(echo "$EVENT_JSON" | jq -r '.tool_input.file_path // empty')

# If no file_path (shouldn't happen for Edit/Write), allow by default
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# High-risk paths requiring documentation review
HIGH_RISK_PATHS=(
    "agent-swarm-monitor/components/"
    "agent-swarm-monitor/app/"
    "backend/api/v1/endpoints/"
    "backend/models/"
    "alembic/versions/"
)

# Check if file is in a high-risk path
IS_HIGH_RISK=false
for path in "${HIGH_RISK_PATHS[@]}"; do
    if [[ "$FILE_PATH" == *"$path"* ]]; then
        IS_HIGH_RISK=true
        break
    fi
done

# If not high-risk, allow immediately
if [ "$IS_HIGH_RISK" = false ]; then
    exit 0
fi

# Check for docs-reviewed flag (session-based)
# Flag file location: /tmp/claude-docs-reviewed-{session_id}
SESSION_ID=$(echo "$EVENT_JSON" | jq -r '.session_id // "unknown"')
FLAG_FILE="/tmp/claude-docs-reviewed-${SESSION_ID}"

if [ -f "$FLAG_FILE" ]; then
    # Docs have been reviewed in this session, allow edit
    exit 0
fi

# BLOCK: Documentation not reviewed
# Exit code 2 = block the action
# Write message to stderr (shown to Claude)

cat >&2 <<'EOF'
⚠️  DOCUMENTATION CHECK REQUIRED

You are attempting to modify a high-risk file without confirming documentation review:

📄 File: $FILE_PATH

🚫 HIGH-RISK AREAS (require mandatory docs check):
   • Frontend components (agent-swarm-monitor/components/, app/)
   • Backend API endpoints (backend/api/v1/endpoints/)
   • Database models (backend/models/, alembic/)

✅ REQUIRED BEFORE MODIFYING THIS FILE:

1. Search for relevant documentation:
   ls docs/ | grep -i [component_name]

2. Read the documentation:
   cat docs/[relevant_doc].md

3. Verify API endpoints exist (if applicable):
   curl http://localhost:8000/docs
   curl -X GET http://localhost:8000/api/v1/[endpoint]

4. Mark documentation as reviewed:
   /docs-reviewed

🔧 RECOVERY COMMANDS:
   • /architecture-first  - Load documentation-first workflow
   • /context-reset       - Emergency context reset + doc search
   • /docs-reviewed       - Mark docs reviewed (allows edits)

📚 RELEVANT DOCUMENTATION:
   • Frontend/API: docs/chat-persistence-api.md
   • System Architecture: docs/SYSTEM_ARCHITECTURE.md
   • Database: docs/POSTGRESQL_MIGRATION.md

⚡ Once you've read the docs, run /docs-reviewed to continue.
EOF

# Replace $FILE_PATH in the error message
sed -i.bak "s|\$FILE_PATH|$FILE_PATH|g" /dev/stderr 2>/dev/null || true

exit 2
