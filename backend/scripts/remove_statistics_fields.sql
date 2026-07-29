-- ============================================
-- 移除原表统计字段脚本
-- 文件: backend/scripts/remove_statistics_fields.sql
-- 创建时间: 2025-12-25
-- 用途: 从原表中移除已迁移到统计表的字段
-- ============================================

BEGIN TRANSACTION;

-- 1. 移除users表的统计字段
-- SQLite不支持直接DROP COLUMN，需要重建表
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

-- 2. 移除tools表的统计字段
CREATE TABLE tools_new AS
SELECT
    id, owner_id, name, slug, description, icon, icon_url,
    category, status, is_public, provider_type, review_status,
    reviewed_at, reviewed_by, reject_reason, current_version_id,
    gpu_required, gpu_memory_mb, timeout_sec,
    created_at, updated_at
FROM tools;

DROP TABLE tools;
ALTER TABLE tools_new RENAME TO tools;

-- 重建索引
CREATE UNIQUE INDEX ix_tools_slug ON tools(slug);
CREATE INDEX ix_tools_owner_id ON tools(owner_id);
CREATE INDEX ix_tools_category ON tools(category);
CREATE INDEX ix_tools_provider_type ON tools(provider_type);
CREATE INDEX ix_tools_review_status ON tools(review_status);

-- 3. 移除files表的统计字段
CREATE TABLE files_new AS
SELECT
    id, owner_id, filename, content_type,
    size_bytes, sha256, storage_backend, storage_path,
    source_type, is_public, is_corrupted, is_permanent,
    expires_at, last_accessed_at, deleted_at,
    reference_count, file_meta,
    created_at, updated_at
FROM files;

DROP TABLE files;
ALTER TABLE files_new RENAME TO files;

-- 重建索引
CREATE INDEX ix_files_owner_id ON files(owner_id);
CREATE INDEX ix_files_sha256 ON files(sha256);

COMMIT;

SELECT 'Statistics fields removed successfully!' as status;
