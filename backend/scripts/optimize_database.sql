-- ============================================
-- SciTool 数据库优化脚本
-- 执行方式: sqlite3 storage/scitool.db < optimize_database.sql
-- 创建时间: 2025-12-25
-- ============================================

-- 1. 启用 WAL 模式（提高并发性能）
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB 缓存
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;

-- 2. 创建高优先级索引

-- tasks 表优化（最重要！）
CREATE INDEX IF NOT EXISTS ix_tasks_queue
ON tasks(status, priority, created_at)
WHERE status IN ('PENDING', 'RUNNING');

CREATE INDEX IF NOT EXISTS ix_tasks_user_status_time
ON tasks(user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_tasks_tool_status
ON tasks(tool_id, status, execution_time_sec);

CREATE INDEX IF NOT EXISTS ix_tasks_finished_at
ON tasks(finished_at)
WHERE finished_at IS NOT NULL;

-- tools 表优化
CREATE INDEX IF NOT EXISTS ix_tools_category_status
ON tools(category, status, is_public);

CREATE INDEX IF NOT EXISTS ix_tools_usage_count
ON tools(usage_count DESC)
WHERE status = 'published' AND is_public = 1;

-- files 表优化
CREATE INDEX IF NOT EXISTS ix_files_expires_at
ON files(expires_at)
WHERE expires_at IS NOT NULL AND is_permanent = 0;

CREATE INDEX IF NOT EXISTS ix_files_sha256_size
ON files(sha256, size_bytes);

CREATE INDEX IF NOT EXISTS ix_files_owner_created
ON files(owner_id, created_at DESC);

-- users 表优化
CREATE INDEX IF NOT EXISTS ix_users_role_status
ON users(role, status);

-- 3. 分析表统计信息
ANALYZE;

-- 4. 输出优化结果
SELECT 'Database optimization completed successfully!' as status;
SELECT 'WAL mode: ' || (SELECT * FROM pragma_journal_mode()) as wal_status;
SELECT 'Total indexes created: ' || COUNT(*) as index_count FROM sqlite_master WHERE type='index';
