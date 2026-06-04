-- 为任务表补充任务名称字段。
ALTER TABLE tasks ADD COLUMN name VARCHAR(120);

-- 为任务名称搜索建立索引。
CREATE INDEX IF NOT EXISTS ix_tasks_name ON tasks (name);
