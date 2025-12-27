-- ============================================
-- 移除tools表统计字段
-- 文件: backend/scripts/remove_tools_statistics.sql
-- ============================================

BEGIN TRANSACTION;

-- 移除tools表的统计字段
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

COMMIT;

SELECT 'Tools statistics fields removed!' as status;
