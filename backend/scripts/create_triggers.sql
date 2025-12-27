-- ============================================
-- 触发器创建脚本
-- 文件: backend/scripts/create_triggers.sql
-- 创建时间: 2025-12-25
-- 用途: 自动维护统计表数据，保证数据一致性
-- ============================================

BEGIN TRANSACTION;

-- ============================================
-- 用户统计触发器
-- ============================================

-- 1. 用户统计触发器：任务创建时
CREATE TRIGGER IF NOT EXISTS trg_user_stats_task_insert
AFTER INSERT ON tasks
FOR EACH ROW
BEGIN
    INSERT INTO user_statistics (user_id, total_tasks, last_task_at, last_updated_at)
    VALUES (NEW.user_id, 1, NEW.created_at, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id) DO UPDATE SET
        total_tasks = total_tasks + 1,
        last_task_at = NEW.created_at,
        last_updated_at = CURRENT_TIMESTAMP;
END;

-- 2. 用户统计触发器：任务完成时
CREATE TRIGGER IF NOT EXISTS trg_user_stats_task_update
AFTER UPDATE OF status ON tasks
FOR EACH ROW
WHEN NEW.status IN ('SUCCESS', 'FAILED') AND OLD.status NOT IN ('SUCCESS', 'FAILED')
BEGIN
    UPDATE user_statistics
    SET
        total_success_tasks = total_success_tasks + CASE WHEN NEW.status = 'SUCCESS' THEN 1 ELSE 0 END,
        total_failed_tasks = total_failed_tasks + CASE WHEN NEW.status = 'FAILED' THEN 1 ELSE 0 END,
        last_updated_at = CURRENT_TIMESTAMP
    WHERE user_id = NEW.user_id;
END;

-- ============================================
-- 工具统计触发器
-- ============================================

-- 3. 工具统计触发器：任务创建时
CREATE TRIGGER IF NOT EXISTS trg_tool_stats_task_insert
AFTER INSERT ON tasks
FOR EACH ROW
BEGIN
    INSERT INTO tool_statistics (tool_id, usage_count, last_used_at, last_updated_at)
    VALUES (NEW.tool_id, 1, NEW.created_at, CURRENT_TIMESTAMP)
    ON CONFLICT(tool_id) DO UPDATE SET
        usage_count = usage_count + 1,
        last_used_at = NEW.created_at,
        last_updated_at = CURRENT_TIMESTAMP;
END;

-- 4. 工具统计触发器：任务完成时（更新成功率和平均执行时间）
CREATE TRIGGER IF NOT EXISTS trg_tool_stats_task_complete
AFTER UPDATE OF status ON tasks
FOR EACH ROW
WHEN NEW.status = 'SUCCESS' AND OLD.status != 'SUCCESS'
BEGIN
    UPDATE tool_statistics
    SET
        success_rate = (
            SELECT CAST(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)
            FROM tasks
            WHERE tool_id = NEW.tool_id AND status IN ('SUCCESS', 'FAILED')
        ),
        avg_execution_time = (
            SELECT AVG(execution_time_sec)
            FROM tasks
            WHERE tool_id = NEW.tool_id AND status = 'SUCCESS' AND execution_time_sec IS NOT NULL
        ),
        last_updated_at = CURRENT_TIMESTAMP
    WHERE tool_id = NEW.tool_id;
END;

COMMIT;

-- 输出结果
SELECT 'Triggers created successfully!' as status;
SELECT 'Total triggers: ' || COUNT(*) as result
FROM sqlite_master
WHERE type='trigger' AND name LIKE 'trg_%_stats_%';
