-- Migration: Create skill_execution_history table
-- Created: 2026-03-07
-- Description: Tracks skill execution history with status, parameters, output, and timing

CREATE TABLE IF NOT EXISTS skill_execution_history (
    execution_id UUID PRIMARY KEY,
    skill_name VARCHAR(255) NOT NULL,
    agent_id UUID,
    status VARCHAR(50) NOT NULL DEFAULT 'RUNNING',
    parameters JSONB,
    output TEXT,
    error_message TEXT,
    execution_time_ms BIGINT,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_skill_execution_agent_id ON skill_execution_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_skill_execution_skill_name ON skill_execution_history(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_execution_status ON skill_execution_history(status);
CREATE INDEX IF NOT EXISTS idx_skill_execution_started_at ON skill_execution_history(started_at DESC);

-- Comments
COMMENT ON TABLE skill_execution_history IS 'Tracks skill execution history with status, parameters, and results';
COMMENT ON COLUMN skill_execution_history.execution_id IS 'Unique execution ID (UUID)';
COMMENT ON COLUMN skill_execution_history.skill_name IS 'Name of the executed skill';
COMMENT ON COLUMN skill_execution_history.agent_id IS 'Agent that executed the skill (optional)';
COMMENT ON COLUMN skill_execution_history.status IS 'Execution status: RUNNING, COMPLETED, FAILED';
COMMENT ON COLUMN skill_execution_history.parameters IS 'Skill execution parameters as JSON';
COMMENT ON COLUMN skill_execution_history.output IS 'Skill execution output (stdout)';
COMMENT ON COLUMN skill_execution_history.error_message IS 'Error message if execution failed';
COMMENT ON COLUMN skill_execution_history.execution_time_ms IS 'Execution time in milliseconds';
COMMENT ON COLUMN skill_execution_history.started_at IS 'When execution started';
COMMENT ON COLUMN skill_execution_history.completed_at IS 'When execution completed (success or failure)';
