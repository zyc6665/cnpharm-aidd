-- ============================================
-- 创建工具分类主数据表
-- ============================================

BEGIN;

CREATE TABLE IF NOT EXISTS tool_categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE tools ADD COLUMN category_id TEXT REFERENCES tool_categories(id);

CREATE INDEX IF NOT EXISTS idx_tool_categories_name ON tool_categories(name);
CREATE INDEX IF NOT EXISTS idx_tool_categories_slug ON tool_categories(slug);
CREATE INDEX IF NOT EXISTS idx_tool_categories_enabled_sort ON tool_categories(is_enabled, sort_order);
CREATE INDEX IF NOT EXISTS idx_tools_category_id ON tools(category_id);

COMMIT;
