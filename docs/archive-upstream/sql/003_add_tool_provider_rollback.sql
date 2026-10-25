-- =====================================================
-- 科学计算工具管理平台 - 工具提供者类型与审核机制回滚脚本
-- =====================================================
-- 版本: v1.1
-- 日期: 2025-12-18
-- 数据库: PostgreSQL 15+
-- 说明: 回滚 003_add_tool_provider.sql 的所有变更
-- 警告: 此脚本会删除新增字段中的数据，请谨慎执行！
-- =====================================================

BEGIN;

-- =====================================================
-- 1. 删除视图
-- =====================================================

DROP VIEW IF EXISTS v_tools_stats_by_provider;
DROP VIEW IF EXISTS v_pending_review_tools;

-- =====================================================
-- 2. 删除触发器和函数
-- =====================================================

DROP TRIGGER IF EXISTS tr_tools_set_review_status ON tools;
DROP FUNCTION IF EXISTS set_tool_review_status();

-- =====================================================
-- 3. 删除约束
-- =====================================================

ALTER TABLE tools DROP CONSTRAINT IF EXISTS chk_tools_public_review;

-- =====================================================
-- 4. 删除索引
-- =====================================================

DROP INDEX IF EXISTS idx_tools_provider_type;
DROP INDEX IF EXISTS idx_tools_review_status;
DROP INDEX IF EXISTS idx_tools_public_approved;
DROP INDEX IF EXISTS idx_tools_platform;

-- =====================================================
-- 5. 删除字段
-- =====================================================

ALTER TABLE tools DROP COLUMN IF EXISTS reject_reason;
ALTER TABLE tools DROP COLUMN IF EXISTS reviewed_by;
ALTER TABLE tools DROP COLUMN IF EXISTS reviewed_at;
ALTER TABLE tools DROP COLUMN IF EXISTS review_status;
ALTER TABLE tools DROP COLUMN IF EXISTS provider_type;

COMMIT;

-- =====================================================
-- 回滚脚本执行完成
-- =====================================================
--
-- 验证命令：
-- \d tools
-- 确认 provider_type, review_status 等字段已删除
-- =====================================================
