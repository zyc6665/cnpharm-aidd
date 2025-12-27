-- =====================================================
-- 科学计算工具管理平台 - 工具提供者类型与审核机制迁移脚本
-- =====================================================
-- 版本: v1.1
-- 日期: 2025-12-18
-- 数据库: PostgreSQL 15+
-- 说明: 新增工具提供者类型和审核机制相关字段
-- 关联文档: docs/design/05-工具系统优化方案.md
-- =====================================================

BEGIN;

-- =====================================================
-- 1. 新增字段到 tools 表
-- =====================================================

-- 1.1 新增 provider_type 字段（工具提供者类型）
-- platform: 平台官方工具
-- user: 用户贡献工具
ALTER TABLE tools
ADD COLUMN IF NOT EXISTS provider_type VARCHAR(20) NOT NULL DEFAULT 'user'
    CHECK (provider_type IN ('platform', 'user'));

COMMENT ON COLUMN tools.provider_type IS '工具提供者类型：platform=平台官方, user=用户贡献';

-- 1.2 新增 review_status 字段（审核状态）
-- not_required: 无需审核（平台官方工具）
-- pending: 待审核
-- approved: 已通过
-- rejected: 已拒绝
ALTER TABLE tools
ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'pending'
    CHECK (review_status IN ('not_required', 'pending', 'approved', 'rejected'));

COMMENT ON COLUMN tools.review_status IS '审核状态：not_required=无需审核, pending=待审核, approved=已通过, rejected=已拒绝';

-- 1.3 新增 reviewed_at 字段（审核时间）
ALTER TABLE tools
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

COMMENT ON COLUMN tools.reviewed_at IS '审核时间';

-- 1.4 新增 reviewed_by 字段（审核人ID）
ALTER TABLE tools
ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL;

COMMENT ON COLUMN tools.reviewed_by IS '审核人ID';

-- 1.5 新增 reject_reason 字段（拒绝原因）
ALTER TABLE tools
ADD COLUMN IF NOT EXISTS reject_reason TEXT;

COMMENT ON COLUMN tools.reject_reason IS '拒绝原因（仅rejected状态有值）';

-- =====================================================
-- 2. 创建索引
-- =====================================================

-- 2.1 按提供者类型查询（首页展示官方工具）
CREATE INDEX IF NOT EXISTS idx_tools_provider_type
    ON tools(provider_type);

-- 2.2 按审核状态查询（管理员审核列表）
CREATE INDEX IF NOT EXISTS idx_tools_review_status
    ON tools(review_status);

-- 2.3 复合索引：公开的已审核用户工具
CREATE INDEX IF NOT EXISTS idx_tools_public_approved
    ON tools(visibility, provider_type, review_status)
    WHERE visibility = 'public';

-- 2.4 复合索引：平台官方工具列表
CREATE INDEX IF NOT EXISTS idx_tools_platform
    ON tools(provider_type, publish_status)
    WHERE provider_type = 'platform';

-- =====================================================
-- 3. 创建触发器：平台官方工具自动设置为无需审核
-- =====================================================

CREATE OR REPLACE FUNCTION set_tool_review_status()
RETURNS TRIGGER AS $$
BEGIN
    -- 平台官方工具自动设置为无需审核
    IF NEW.provider_type = 'platform' THEN
        NEW.review_status := 'not_required';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 删除旧触发器（如果存在）
DROP TRIGGER IF EXISTS tr_tools_set_review_status ON tools;

-- 创建新触发器
CREATE TRIGGER tr_tools_set_review_status
    BEFORE INSERT OR UPDATE OF provider_type ON tools
    FOR EACH ROW
    EXECUTE FUNCTION set_tool_review_status();

COMMENT ON FUNCTION set_tool_review_status() IS '自动设置平台官方工具的审核状态为not_required';

-- =====================================================
-- 4. 添加业务约束：用户工具公开需先审核通过
-- =====================================================

-- 注意：如果已存在不符合约束的数据，需要先修复数据再添加约束
-- 先检查是否有违反约束的数据
DO $$
DECLARE
    violation_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO violation_count
    FROM tools
    WHERE provider_type = 'user'
      AND visibility = 'public'
      AND review_status NOT IN ('approved', 'not_required');

    IF violation_count > 0 THEN
        RAISE NOTICE '发现 % 条违反约束的数据，将自动修复为已通过状态', violation_count;

        -- 自动修复：将已公开的用户工具设为已通过
        UPDATE tools
        SET review_status = 'approved',
            reviewed_at = NOW()
        WHERE provider_type = 'user'
          AND visibility = 'public'
          AND review_status NOT IN ('approved', 'not_required');
    END IF;
END $$;

-- 添加约束
ALTER TABLE tools
DROP CONSTRAINT IF EXISTS chk_tools_public_review;

ALTER TABLE tools
ADD CONSTRAINT chk_tools_public_review
CHECK (
    -- 平台官方工具可直接公开
    provider_type = 'platform' OR
    -- 用户工具需审核通过才能公开（或保持私有）
    (provider_type = 'user' AND (visibility = 'private' OR review_status = 'approved'))
);

-- =====================================================
-- 5. 迁移现有数据
-- =====================================================

-- 5.1 将所有现有工具设为平台官方工具（因为之前只有管理员能创建）
UPDATE tools
SET provider_type = 'platform',
    review_status = 'not_required'
WHERE provider_type = 'user'
  AND review_status = 'pending';

RAISE NOTICE '已将现有工具迁移为平台官方工具';

-- =====================================================
-- 6. 创建审核相关视图
-- =====================================================

-- 6.1 待审核工具视图（管理员使用）
CREATE OR REPLACE VIEW v_pending_review_tools AS
SELECT
    t.id,
    t.name,
    t.slug,
    t.description,
    t.owner_id,
    u.display_name AS owner_name,
    u.email AS owner_email,
    t.created_at,
    t.updated_at,
    EXTRACT(DAY FROM (NOW() - t.created_at)) AS pending_days
FROM tools t
JOIN users u ON t.owner_id = u.id
WHERE t.provider_type = 'user'
  AND t.review_status = 'pending'
ORDER BY t.created_at ASC;

COMMENT ON VIEW v_pending_review_tools IS '待审核的用户工具列表（管理员审核队列）';

-- 6.2 工具统计视图（按提供者类型）
CREATE OR REPLACE VIEW v_tools_stats_by_provider AS
SELECT
    provider_type,
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE visibility = 'public') AS public_count,
    COUNT(*) FILTER (WHERE review_status = 'pending') AS pending_review_count,
    COUNT(*) FILTER (WHERE review_status = 'approved') AS approved_count,
    COUNT(*) FILTER (WHERE review_status = 'rejected') AS rejected_count
FROM tools
GROUP BY provider_type;

COMMENT ON VIEW v_tools_stats_by_provider IS '按提供者类型统计工具数量';

COMMIT;

-- =====================================================
-- 迁移脚本执行完成
-- =====================================================
--
-- 验证命令：
-- SELECT provider_type, review_status, COUNT(*)
-- FROM tools
-- GROUP BY provider_type, review_status;
--
-- 回滚命令（如需）：
-- \i docs/sql/003_add_tool_provider_rollback.sql
-- =====================================================
