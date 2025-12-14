-- =====================================================
-- 科学计算工具管理平台 - 数据库初始化脚本
-- =====================================================
-- 版本: v1.0
-- 日期: 2025-12-14
-- 数据库: PostgreSQL 15+
-- =====================================================

BEGIN;

-- =====================================================
-- 1. 启用扩展
-- =====================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID生成
CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- 加密函数
CREATE EXTENSION IF NOT EXISTS "citext";         -- 不区分大小写文本
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";  -- 慢查询统计

-- =====================================================
-- 2. 创建通用函数
-- =====================================================

-- 自动更新updated_at字段
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 3. 用户相关表
-- =====================================================

-- 3.1 users（用户表）
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email CITEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'vip', 'admin')),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_created_at ON users(created_at DESC);
CREATE INDEX idx_users_status_created ON users(status, created_at DESC);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE users IS '用户基本信息表';
COMMENT ON COLUMN users.email IS '邮箱（不区分大小写）';
COMMENT ON COLUMN users.password_hash IS '密码哈希（Bcrypt）';
COMMENT ON COLUMN users.role IS '角色：user/vip/admin';
COMMENT ON COLUMN users.status IS '状态：active/disabled';

-- 3.2 user_sessions（用户会话表）
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_token TEXT NOT NULL UNIQUE,
    is_guest BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_sessions_expires_at ON user_sessions(expires_at);

COMMENT ON TABLE user_sessions IS '用户会话表（含游客会话）';
COMMENT ON COLUMN user_sessions.is_guest IS '是否游客会话';

-- 3.3 credit_logs（积分日志表 - 预留）
CREATE TABLE IF NOT EXISTS credit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    transaction_type VARCHAR(50) NOT NULL
        CHECK (transaction_type IN ('recharge', 'deduct', 'refund', 'gift', 'expire')),
    description TEXT,
    related_task_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_credit_logs_user_id ON credit_logs(user_id, created_at DESC);

COMMENT ON TABLE credit_logs IS '积分变动日志（预留）';

-- =====================================================
-- 4. 工具相关表
-- =====================================================

-- 4.1 tools（工具表）
CREATE TABLE IF NOT EXISTS tools (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    slug VARCHAR(160) NOT NULL UNIQUE,
    description TEXT,
    visibility VARCHAR(20) NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('public', 'private')),
    publish_status VARCHAR(20) NOT NULL DEFAULT 'enabled'
        CHECK (publish_status IN ('enabled', 'disabled')),
    current_version_id UUID,
    favorites_count INTEGER NOT NULL DEFAULT 0,
    runs_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tools_owner ON tools(owner_id);
CREATE INDEX idx_tools_visibility ON tools(visibility, publish_status);
CREATE INDEX idx_tools_created_at ON tools(created_at DESC);

CREATE TRIGGER trg_tools_updated_at
    BEFORE UPDATE ON tools
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE tools IS '工具基本信息表';
COMMENT ON COLUMN tools.slug IS 'URL友好标识符';
COMMENT ON COLUMN tools.visibility IS '可见性：public/private';
COMMENT ON COLUMN tools.current_version_id IS '当前版本ID';

-- 4.2 tool_versions（工具版本表）
CREATE TABLE IF NOT EXISTS tool_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_id UUID NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
    version VARCHAR(40) NOT NULL,
    config JSONB NOT NULL,
    notes TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tool_id, version)
);

CREATE INDEX idx_tool_versions_tool ON tool_versions(tool_id, created_at DESC);
CREATE INDEX idx_tool_versions_config ON tool_versions USING GIN (config);

COMMENT ON TABLE tool_versions IS '工具版本和配置表';
COMMENT ON COLUMN tool_versions.config IS '工具配置（JSONB格式）';

-- 添加外键约束（tools.current_version_id）
ALTER TABLE tools
    ADD CONSTRAINT fk_tools_current_version
    FOREIGN KEY (current_version_id) REFERENCES tool_versions(id) ON DELETE SET NULL;

-- 4.3 tags（标签表）
CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE tags IS '工具分类标签表';

-- 4.4 tool_tag_map（工具标签映射表）
CREATE TABLE IF NOT EXISTS tool_tag_map (
    tool_id UUID NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tool_id, tag_id)
);

CREATE INDEX idx_tool_tag_map_tag ON tool_tag_map(tag_id);

COMMENT ON TABLE tool_tag_map IS '工具标签多对多映射表';

-- 4.5 tool_favorites（工具收藏表）
CREATE TABLE IF NOT EXISTS tool_favorites (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_id UUID NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tool_id)
);

CREATE INDEX idx_tool_favorites_tool ON tool_favorites(tool_id);

COMMENT ON TABLE tool_favorites IS '用户收藏的工具';

-- 触发器：自动更新tool的favorites_count
CREATE OR REPLACE FUNCTION update_tool_favorites_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE tools SET favorites_count = favorites_count + 1 WHERE id = NEW.tool_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE tools SET favorites_count = favorites_count - 1 WHERE id = OLD.tool_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tool_favorites_count
    AFTER INSERT OR DELETE ON tool_favorites
    FOR EACH ROW
    EXECUTE FUNCTION update_tool_favorites_count();

-- =====================================================
-- 5. 任务相关表
-- =====================================================

-- 5.1 tasks（任务表）
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    tool_id UUID NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
    tool_version_id UUID NOT NULL REFERENCES tool_versions(id) ON DELETE CASCADE,
    job_name VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILURE', 'CANCELED')),
    priority VARCHAR(20) NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('low', 'normal', 'high')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    execution_time_sec INTEGER,
    error_message TEXT
);

CREATE INDEX idx_tasks_user ON tasks(user_id, created_at DESC);
CREATE INDEX idx_tasks_tool ON tasks(tool_id, created_at DESC);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status, created_at DESC);
CREATE INDEX idx_tasks_active ON tasks(created_at DESC)
    WHERE status IN ('PENDING', 'RUNNING');

COMMENT ON TABLE tasks IS '任务主表';
COMMENT ON COLUMN tasks.status IS '任务状态：PENDING/RUNNING/SUCCESS/FAILURE/CANCELED';
COMMENT ON COLUMN tasks.priority IS '优先级：low/normal/high';

-- 5.2 task_inputs（任务输入表）
CREATE TABLE IF NOT EXISTS task_inputs (
    task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    params JSONB NOT NULL,
    file_ids JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE task_inputs IS '任务输入参数和文件';

-- 5.3 task_outputs（任务输出表）
CREATE TABLE IF NOT EXISTS task_outputs (
    task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    raw_output JSONB,
    normalized_output JSONB,
    output_file_ids JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE task_outputs IS '任务输出结果';

-- 5.4 task_logs（任务日志表）
CREATE TABLE IF NOT EXISTS task_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL DEFAULT 'INFO'
        CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    context JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_logs_task ON task_logs(task_id, created_at DESC);

COMMENT ON TABLE task_logs IS '任务执行日志';

-- 5.5 task_gpu_allocations（任务GPU分配表）
CREATE TABLE IF NOT EXISTS task_gpu_allocations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    gpu_node_id UUID NOT NULL,
    gpu_index INTEGER NOT NULL,
    memory_allocated_mb INTEGER NOT NULL,
    allocated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_at TIMESTAMPTZ
);

CREATE INDEX idx_gpu_alloc_task ON task_gpu_allocations(task_id);
CREATE INDEX idx_gpu_alloc_node ON task_gpu_allocations(gpu_node_id, allocated_at DESC);

COMMENT ON TABLE task_gpu_allocations IS '任务GPU资源分配记录';

-- =====================================================
-- 6. 文件相关表
-- =====================================================

-- 6.1 files（文件表）
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    source_type VARCHAR(20) NOT NULL
        CHECK (source_type IN ('user_input', 'tool_output', 'temp')),
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 VARCHAR(64) NOT NULL UNIQUE,
    storage_path VARCHAR(500) NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_files_owner ON files(owner_id, created_at DESC);
CREATE INDEX idx_files_expires_at ON files(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_files_active ON files(owner_id, created_at DESC)
    WHERE expires_at IS NULL OR expires_at > NOW();

COMMENT ON TABLE files IS '文件元数据表';
COMMENT ON COLUMN files.sha256 IS 'SHA256哈希（用于去重）';
COMMENT ON COLUMN files.storage_path IS 'MinIO存储路径';

-- 6.2 file_access_logs（文件访问日志表）
CREATE TABLE IF NOT EXISTS file_access_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(20) NOT NULL
        CHECK (action IN ('upload', 'download', 'delete', 'view')),
    ip_address VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_file_access_logs_file ON file_access_logs(file_id, created_at DESC);

COMMENT ON TABLE file_access_logs IS '文件访问日志（安全审计）';

-- =====================================================
-- 7. GPU资源相关表
-- =====================================================

-- 7.1 gpu_nodes（GPU节点表）
CREATE TABLE IF NOT EXISTS gpu_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hostname VARCHAR(255) NOT NULL UNIQUE,
    gpu_name VARCHAR(100) NOT NULL,
    gpu_count INTEGER NOT NULL,
    total_memory_mb INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'online'
        CHECK (status IN ('online', 'offline', 'maintenance')),
    metadata JSONB,
    last_heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gpu_nodes_status ON gpu_nodes(status);

COMMENT ON TABLE gpu_nodes IS 'GPU服务器节点注册表';
COMMENT ON COLUMN gpu_nodes.metadata IS '元数据（CUDA版本、驱动等）';

-- 添加外键约束（task_gpu_allocations.gpu_node_id）
ALTER TABLE task_gpu_allocations
    ADD CONSTRAINT fk_gpu_alloc_node
    FOREIGN KEY (gpu_node_id) REFERENCES gpu_nodes(id) ON DELETE CASCADE;

-- 7.2 gpu_usage_stats（GPU使用统计表）
CREATE TABLE IF NOT EXISTS gpu_usage_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gpu_node_id UUID NOT NULL REFERENCES gpu_nodes(id) ON DELETE CASCADE,
    gpu_index INTEGER NOT NULL,
    utilization_percent REAL NOT NULL,
    memory_used_mb INTEGER NOT NULL,
    memory_free_mb INTEGER NOT NULL,
    temperature_celsius REAL,
    power_watts INTEGER,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gpu_stats_node ON gpu_usage_stats(gpu_node_id, recorded_at DESC);

COMMENT ON TABLE gpu_usage_stats IS 'GPU使用率统计（时序数据）';

-- =====================================================
-- 8. 系统配置表
-- =====================================================

CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    value_type VARCHAR(20) NOT NULL
        CHECK (value_type IN ('string', 'integer', 'float', 'boolean', 'json')),
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE system_config IS '系统全局配置表';

-- =====================================================
-- 9. 视图（可选）
-- =====================================================

-- 9.1 活跃任务视图
CREATE OR REPLACE VIEW v_active_tasks AS
SELECT
    t.id,
    t.user_id,
    u.email AS user_email,
    t.tool_id,
    tl.name AS tool_name,
    t.tool_version_id,
    tv.version AS tool_version,
    t.status,
    t.priority,
    t.created_at,
    t.started_at,
    EXTRACT(EPOCH FROM (NOW() - t.started_at))::INTEGER AS running_seconds
FROM tasks t
LEFT JOIN users u ON t.user_id = u.id
LEFT JOIN tools tl ON t.tool_id = tl.id
LEFT JOIN tool_versions tv ON t.tool_version_id = tv.id
WHERE t.status IN ('PENDING', 'RUNNING');

COMMENT ON VIEW v_active_tasks IS '活跃任务视图（待执行和执行中）';

-- 9.2 GPU节点状态视图
CREATE OR REPLACE VIEW v_gpu_node_status AS
SELECT
    gn.id,
    gn.hostname,
    gn.gpu_name,
    gn.gpu_count,
    gn.total_memory_mb,
    gn.status,
    COUNT(DISTINCT tga.id) AS active_allocations,
    gn.last_heartbeat_at,
    CASE
        WHEN gn.last_heartbeat_at IS NULL THEN 'never'
        WHEN gn.last_heartbeat_at < NOW() - INTERVAL '5 minutes' THEN 'stale'
        ELSE 'healthy'
    END AS heartbeat_status
FROM gpu_nodes gn
LEFT JOIN task_gpu_allocations tga
    ON gn.id = tga.gpu_node_id AND tga.released_at IS NULL
GROUP BY gn.id;

COMMENT ON VIEW v_gpu_node_status IS 'GPU节点状态视图（含活跃分配数）';

-- =====================================================
-- 10. 权限设置（可选）
-- =====================================================

-- 创建只读用户（用于数据分析、监控）
-- CREATE ROLE scitool_readonly WITH LOGIN PASSWORD 'readonly_password';
-- GRANT CONNECT ON DATABASE scitool_platform TO scitool_readonly;
-- GRANT USAGE ON SCHEMA public TO scitool_readonly;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO scitool_readonly;

COMMIT;

-- =====================================================
-- 初始化脚本执行完成
-- =====================================================
