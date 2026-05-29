-- ============================================
-- 验证工具工作台分组迁移结果
-- ============================================

SELECT
    'tool_workbench_group_count' AS check_name,
    COUNT(*) AS value
FROM tool_workbench_groups;

SELECT
    'tool_workbench_group_mapping_count' AS check_name,
    COUNT(*) AS value
FROM tool_workbench_group_mappings;

SELECT
    'dangling_tool_workbench_group_refs' AS check_name,
    COUNT(*) AS value
FROM tool_workbench_group_mappings AS twgm
LEFT JOIN tool_workbench_groups AS twg ON twg.id = twgm.group_id
WHERE twg.id IS NULL;

SELECT
    'dangling_tool_refs' AS check_name,
    COUNT(*) AS value
FROM tool_workbench_group_mappings AS twgm
LEFT JOIN tools AS t ON t.id = twgm.tool_id
WHERE t.id IS NULL;

SELECT
    'duplicate_tool_group_mappings' AS check_name,
    COUNT(*) AS value
FROM (
    SELECT
        tool_id,
        group_id
    FROM tool_workbench_group_mappings
    GROUP BY tool_id, group_id
    HAVING COUNT(*) > 1
);

SELECT
    id,
    name,
    slug,
    sort_order,
    is_enabled
FROM tool_workbench_groups
ORDER BY sort_order ASC, name ASC;

PRAGMA foreign_key_check;
