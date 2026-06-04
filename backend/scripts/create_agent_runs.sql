CREATE TABLE IF NOT EXISTS agent_runs (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    message TEXT NOT NULL,
    intent VARCHAR(100) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    input_type VARCHAR(64) NOT NULL,
    input_file_id VARCHAR(36),
    requested_outputs JSON NOT NULL DEFAULT '[]',
    plan JSON NOT NULL DEFAULT '{}',
    summary TEXT,
    error_message TEXT,
    finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(input_file_id) REFERENCES files(id)
);

CREATE INDEX IF NOT EXISTS ix_agent_runs_user_id ON agent_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_agent_runs_intent ON agent_runs(intent);
CREATE INDEX IF NOT EXISTS ix_agent_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS ix_agent_runs_input_file_id ON agent_runs(input_file_id);

CREATE TABLE IF NOT EXISTS agent_run_steps (
    id VARCHAR(36) PRIMARY KEY,
    agent_run_id VARCHAR(36) NOT NULL,
    step_key VARCHAR(100) NOT NULL,
    tool_slug VARCHAR(100) NOT NULL,
    tool_id VARCHAR(36),
    task_id VARCHAR(36),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    sort_order INTEGER NOT NULL DEFAULT 0,
    depends_on_step_ids JSON NOT NULL DEFAULT '[]',
    semantic_inputs JSON NOT NULL DEFAULT '{}',
    semantic_outputs JSON NOT NULL DEFAULT '{}',
    params JSON NOT NULL DEFAULT '{}',
    input_file_ids JSON NOT NULL DEFAULT '[]',
    output_file_ids JSON NOT NULL DEFAULT '[]',
    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(agent_run_id) REFERENCES agent_runs(id),
    FOREIGN KEY(tool_id) REFERENCES tools(id),
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS ix_agent_run_steps_agent_run_id ON agent_run_steps(agent_run_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_steps_step_key ON agent_run_steps(step_key);
CREATE INDEX IF NOT EXISTS ix_agent_run_steps_tool_slug ON agent_run_steps(tool_slug);
CREATE INDEX IF NOT EXISTS ix_agent_run_steps_tool_id ON agent_run_steps(tool_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_steps_task_id ON agent_run_steps(task_id);
CREATE INDEX IF NOT EXISTS ix_agent_run_steps_status ON agent_run_steps(status);
