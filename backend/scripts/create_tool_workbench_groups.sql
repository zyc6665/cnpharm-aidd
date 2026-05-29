-- ============================================
-- 创建工具工作台分组主数据表与映射表
-- ============================================

BEGIN;

CREATE TABLE IF NOT EXISTS tool_workbench_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_workbench_group_mappings (
    id TEXT PRIMARY KEY,
    tool_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_recommended INTEGER NOT NULL DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE,
    FOREIGN KEY(group_id) REFERENCES tool_workbench_groups(id) ON DELETE CASCADE,
    UNIQUE (tool_id, group_id)
);

CREATE INDEX IF NOT EXISTS idx_tool_workbench_groups_name
    ON tool_workbench_groups(name);
CREATE INDEX IF NOT EXISTS idx_tool_workbench_groups_slug
    ON tool_workbench_groups(slug);
CREATE INDEX IF NOT EXISTS idx_tool_workbench_groups_enabled_sort
    ON tool_workbench_groups(is_enabled, sort_order);
CREATE INDEX IF NOT EXISTS idx_tool_workbench_group_mappings_tool_id
    ON tool_workbench_group_mappings(tool_id);
CREATE INDEX IF NOT EXISTS idx_tool_workbench_group_mappings_group_id
    ON tool_workbench_group_mappings(group_id);
CREATE INDEX IF NOT EXISTS idx_tool_workbench_group_mappings_enabled_sort
    ON tool_workbench_group_mappings(is_enabled, sort_order);

COMMIT;
