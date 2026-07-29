-- ============================================
-- 移除files表统计字段（修正版）
-- 文件: backend/scripts/remove_files_statistics.sql
-- ============================================

BEGIN TRANSACTION;

-- 移除files表的download_count字段
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
CREATE INDEX IF NOT EXISTS ix_files_owner_id ON files(owner_id);
CREATE INDEX IF NOT EXISTS ix_files_sha256 ON files(sha256);

COMMIT;

SELECT 'Files statistics field removed!' as status;
