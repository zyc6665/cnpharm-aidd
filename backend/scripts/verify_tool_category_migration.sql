-- ============================================
-- 验证工具分类迁移结果
-- ============================================

SELECT
    'tool_category_count' AS check_name,
    COUNT(*) AS value
FROM tool_categories;

SELECT
    'tools_without_category_id' AS check_name,
    COUNT(*) AS value
FROM tools
WHERE category_id IS NULL;

SELECT
    'dangling_tool_category_refs' AS check_name,
    COUNT(*) AS value
FROM tools AS t
LEFT JOIN tool_categories AS tc ON tc.id = t.category_id
WHERE t.category_id IS NOT NULL
  AND tc.id IS NULL;

SELECT
    id,
    name,
    slug,
    sort_order,
    is_enabled
FROM tool_categories
ORDER BY sort_order ASC, name ASC;

PRAGMA foreign_key_check;
