CREATE TABLE IF NOT EXISTS model_services (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(50) NOT NULL DEFAULT 'openai_compatible',
    base_url VARCHAR(500) NOT NULL,
    api_key_encrypted TEXT,
    model_name VARCHAR(200) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT 0,
    is_enabled BOOLEAN NOT NULL DEFAULT 1,
    timeout_seconds INTEGER NOT NULL DEFAULT 60,
    max_tokens INTEGER NOT NULL DEFAULT 2048,
    temperature FLOAT NOT NULL DEFAULT 0.2,
    last_test_status VARCHAR(32),
    last_test_message TEXT,
    last_tested_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_model_services_is_default ON model_services (is_default);
CREATE INDEX IF NOT EXISTS ix_model_services_is_enabled ON model_services (is_enabled);
