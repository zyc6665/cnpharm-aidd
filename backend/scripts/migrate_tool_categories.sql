-- ============================================
-- 回填工具分类主数据与外键
-- ============================================

BEGIN;

WITH normalized_categories AS (
    SELECT DISTINCT
        TRIM(COALESCE(NULLIF(category, ''), 'Uncategorized')) AS category_name,
        LOWER(REPLACE(TRIM(COALESCE(NULLIF(category, ''), 'uncategorized')), ' ', '-')) AS base_slug
    FROM tools
),
ranked_categories AS (
    SELECT
        category_name,
        base_slug,
        ROW_NUMBER() OVER (PARTITION BY base_slug ORDER BY category_name) AS slug_rank
    FROM normalized_categories
)
INSERT OR IGNORE INTO tool_categories (
    id,
    name,
    slug,
    description,
    sort_order,
    is_enabled,
    created_at,
    updated_at
)
SELECT
    LOWER(HEX(RANDOMBLOB(16))),
    category_name,
    CASE
        WHEN slug_rank = 1 THEN base_slug
        ELSE base_slug || '-' || slug_rank
    END,
    NULL,
    ROW_NUMBER() OVER (ORDER BY category_name),
    CASE
        WHEN base_slug = 'uncategorized' THEN 0
        ELSE 1
    END,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM ranked_categories;

UPDATE tools
SET category_id = (
    SELECT tc.id
    FROM tool_categories AS tc
    WHERE tc.name = TRIM(COALESCE(NULLIF(tools.category, ''), 'Uncategorized'))
)
WHERE category_id IS NULL;

COMMIT;
