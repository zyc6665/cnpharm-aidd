-- ============================================
-- 移除users表统计字段
-- 文件: backend/scripts/remove_users_statistics.sql
-- ============================================

BEGIN TRANSACTION;

-- 移除users表的统计字段
CREATE TABLE users_new AS
SELECT
    id, email, password_hash, display_name, avatar_url,
    role, status, daily_task_limit, max_file_size_mb,
    created_at, updated_at
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

-- 重建索引
CREATE UNIQUE INDEX ix_users_email ON users(email);

COMMIT;

SELECT 'Users statistics fields removed!' as status;
