-- ============================================
-- 统计表创建脚本
-- 文件: backend/scripts/create_statistics_tables.sql
-- 创建时间: 2025-12-25
-- 用途: 将统计字段从主表分离到独立表，符合第三范式
-- ============================================

BEGIN TRANSACTION;

-- 1. 用户统计表
CREATE TABLE IF NOT EXISTS user_statistics (
    user_id VARCHAR(36) PRIMARY KEY,
    total_tasks INTEGER DEFAULT 0,
    total_success_tasks INTEGER DEFAULT 0,
    total_failed_tasks INTEGER DEFAULT 0,
    total_credits_used FLOAT DEFAULT 0.0,
    last_task_at DATETIME,
    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_user_statistics_updated ON user_statistics(last_updated_at);

-- 2. 工具统计表
CREATE TABLE IF NOT EXISTS tool_statistics (
    tool_id VARCHAR(36) PRIMARY KEY,
    usage_count INTEGER DEFAULT 0,
    favorite_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    success_rate FLOAT DEFAULT 0.0,
    avg_execution_time FLOAT DEFAULT 0.0,
    last_used_at DATETIME,
    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_tool_statistics_usage ON tool_statistics(usage_count DESC);
CREATE INDEX IF NOT EXISTS ix_tool_statistics_updated ON tool_statistics(last_updated_at);

-- 3. 文件统计表
CREATE TABLE IF NOT EXISTS file_statistics (
    file_id VARCHAR(36) PRIMARY KEY,
    download_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    last_download_at DATETIME,
    last_view_at DATETIME,
    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_file_statistics_download ON file_statistics(download_count DESC);
CREATE INDEX IF NOT EXISTS ix_file_statistics_updated ON file_statistics(last_updated_at);

-- 4. 迁移现有数据
INSERT OR IGNORE INTO user_statistics (user_id, total_tasks, total_success_tasks, last_updated_at)
SELECT id, COALESCE(total_tasks, 0), COALESCE(total_success_tasks, 0), datetime('now')
FROM users;

INSERT OR IGNORE INTO tool_statistics (tool_id, usage_count, favorite_count, view_count, last_updated_at)
SELECT id, COALESCE(usage_count, 0), COALESCE(favorite_count, 0), COALESCE(view_count, 0), datetime('now')
FROM tools;

INSERT OR IGNORE INTO file_statistics (file_id, download_count, last_updated_at)
SELECT id, COALESCE(download_count, 0), datetime('now')
FROM files;

COMMIT;

-- 5. 输出结果
SELECT 'Statistics tables created successfully!' as status;
SELECT 'User statistics: ' || COUNT(*) || ' records' as result FROM user_statistics;
SELECT 'Tool statistics: ' || COUNT(*) || ' records' as result FROM tool_statistics;
SELECT 'File statistics: ' || COUNT(*) || ' records' as result FROM file_statistics;
