#!/bin/bash
# .claude/hooks/mark-docs-reviewed.sh
# Helper script to mark documentation as reviewed
# Creates a session flag that allows high-risk file edits

set -e

# Get session ID from environment or generate one
# Claude Code should provide this, but fallback to generating one
if [ -z "$CLAUDE_SESSION_ID" ]; then
    # Try to read from .claude/session file if it exists
    if [ -f ".claude/session" ]; then
        SESSION_ID=$(cat .claude/session)
    else
        # Generate a session ID based on current time
        SESSION_ID="manual-$(date +%s)"
        # Save it for consistency in this session
        mkdir -p .claude
        echo "$SESSION_ID" > .claude/session
    fi
else
    SESSION_ID="$CLAUDE_SESSION_ID"
fi

FLAG_FILE="/tmp/claude-docs-reviewed-${SESSION_ID}"

# Create the flag file
touch "$FLAG_FILE"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$FLAG_FILE"

echo "✅ Documentation marked as reviewed for session: $SESSION_ID"
echo ""
echo "📝 Effect: High-risk file edits are now ALLOWED for:"
echo "   • Frontend components (agent-swarm-monitor/)"
echo "   • Backend API endpoints (backend/api/v1/endpoints/)"
echo "   • Database models (backend/models/)"
echo ""
echo "⏱️  Flag expires when: Session ends or Claude Code restarts"
echo ""
echo "🚀 You can now confidently modify high-risk files."
