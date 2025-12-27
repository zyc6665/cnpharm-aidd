-- ============================================
-- 数据迁移验证脚本
-- 文件: backend/scripts/verify_migration.sql
-- 创建时间: 2025-12-25
-- 用途: 验证统计表数据迁移的正确性和一致性
-- ============================================

-- 1. 验证用户统计数据一致性
SELECT
    '用户统计验证' as check_type,
    COUNT(*) as total_users,
    SUM(CASE WHEN u.total_tasks = COALESCE(us.total_tasks, 0) THEN 1 ELSE 0 END) as matched_count,
    SUM(CASE WHEN u.total_tasks != COALESCE(us.total_tasks, 0) THEN 1 ELSE 0 END) as mismatched_count
FROM users u
LEFT JOIN user_statistics us ON us.user_id = u.id;

-- 2. 验证工具统计数据一致性
SELECT
    '工具统计验证' as check_type,
    COUNT(*) as total_tools,
    SUM(CASE WHEN t.usage_count = COALESCE(ts.usage_count, 0) THEN 1 ELSE 0 END) as matched_count,
    SUM(CASE WHEN t.usage_count != COALESCE(ts.usage_count, 0) THEN 1 ELSE 0 END) as mismatched_count
FROM tools t
LEFT JOIN tool_statistics ts ON ts.tool_id = t.id;

-- 3. 验证文件统计数据一致性
SELECT
    '文件统计验证' as check_type,
    COUNT(*) as total_files,
    SUM(CASE WHEN f.download_count = COALESCE(fs.download_count, 0) THEN 1 ELSE 0 END) as matched_count,
    SUM(CASE WHEN f.download_count != COALESCE(fs.download_count, 0) THEN 1 ELSE 0 END) as mismatched_count
FROM files f
LEFT JOIN file_statistics fs ON fs.file_id = f.id;

-- 4. 检查外键约束
PRAGMA foreign_key_check;

-- 5. 检查数据库完整性
PRAGMA integrity_check;

-- 6. 显示表大小统计
SELECT
    name as table_name,
    ROUND(SUM(pgsize) / 1024.0 / 1024.0, 2) as size_mb,
    COUNT(*) as page_count
FROM dbstat
WHERE name IN ('users', 'user_statistics', 'tools', 'tool_statistics', 'files', 'file_statistics')
GROUP BY name
ORDER BY size_mb DESC;

-- 7. 显示统计表记录数
SELECT 'user_statistics' as table_name, COUNT(*) as record_count FROM user_statistics
UNION ALL
SELECT 'tool_statistics', COUNT(*) FROM tool_statistics
UNION ALL
SELECT 'file_statistics', COUNT(*) FROM file_statistics;
