-- =====================================================
-- 科学计算工具管理平台 - 种子数据脚本
-- =====================================================
-- 版本: v1.0
-- 日期: 2025-12-14
-- 说明: 插入初始数据，用于开发和测试
-- =====================================================

BEGIN;

-- =====================================================
-- 1. 默认标签
-- =====================================================

INSERT INTO tags (id, name, description) VALUES
    ('11111111-1111-1111-1111-111111111111', 'AI', '人工智能相关工具'),
    ('22222222-2222-2222-2222-222222222222', 'Protein', '蛋白质相关工具'),
    ('33333333-3333-3333-3333-333333333333', 'Molecule', '分子相关工具'),
    ('44444444-4444-4444-4444-444444444444', 'Docking', '对接相关工具'),
    ('55555555-5555-5555-5555-555555555555', 'Prediction', '预测相关工具'),
    ('66666666-6666-6666-6666-666666666666', 'Visualization', '可视化工具'),
    ('77777777-7777-7777-7777-777777777777', 'Simulation', '模拟仿真工具'),
    ('88888888-8888-8888-8888-888888888888', 'Analysis', '分析工具')
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- 2. 系统配置
-- =====================================================

INSERT INTO system_config (key, value, value_type, description) VALUES
    -- 任务配额
    ('guest_daily_task_limit', '5', 'integer', '游客每日任务配额'),
    ('user_daily_task_limit', '50', 'integer', '普通用户每日任务配额'),
    ('vip_daily_task_limit', '999999', 'integer', 'VIP用户每日任务配额（无限制）'),

    -- 文件上传限制
    ('max_file_size_guest_mb', '10', 'integer', '游客最大文件上传大小（MB）'),
    ('max_file_size_user_mb', '100', 'integer', '普通用户最大文件上传大小（MB）'),
    ('max_file_size_vip_mb', '1024', 'integer', 'VIP用户最大文件上传大小（MB）'),

    -- 文件保留时间
    ('file_retention_days_guest', '7', 'integer', '游客文件保留天数'),
    ('file_retention_days_user', '30', 'integer', '普通用户文件保留天数'),
    ('file_retention_days_vip', '90', 'integer', 'VIP用户文件保留天数'),

    -- 任务配置
    ('task_timeout_sec', '600', 'integer', '任务默认超时时间（秒）'),
    ('task_max_retries', '3', 'integer', '任务最大重试次数'),

    -- GPU配置
    ('gpu_default_memory_mb', '8000', 'integer', '默认GPU显存需求（MB）'),
    ('gpu_heartbeat_timeout_sec', '300', 'integer', 'GPU节点心跳超时时间（秒）'),

    -- 系统信息
    ('platform_name', '科学计算工具管理平台', 'string', '平台名称'),
    ('platform_version', '1.0.0-MVP', 'string', '平台版本'),
    ('maintenance_mode', 'false', 'boolean', '维护模式开关')
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

-- =====================================================
-- 3. 默认管理员用户（仅开发环境使用）
-- =====================================================

-- 密码: Admin@123456
-- 哈希值由 bcrypt 生成（cost=12）
INSERT INTO users (id, email, password_hash, display_name, role, status) VALUES
    (
        '00000000-0000-0000-0000-000000000001',
        'admin@example.com',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5isiXPH.j8TKm',  -- Admin@123456
        'System Administrator',
        'admin',
        'active'
    )
ON CONFLICT (email) DO NOTHING;

-- =====================================================
-- 4. 示例工具（可选，仅开发环境）
-- =====================================================

-- 4.1 示例工具1：蛋白质结构预测
INSERT INTO tools (id, owner_id, name, slug, description, visibility, publish_status) VALUES
    (
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        '00000000-0000-0000-0000-000000000001',
        'Protein Structure Predictor',
        'protein-structure-predictor',
        '基于深度学习的蛋白质结构预测工具，支持从序列预测三维结构。',
        'public',
        'enabled'
    )
ON CONFLICT (slug) DO NOTHING;

-- 工具版本
INSERT INTO tool_versions (id, tool_id, version, config, notes, created_by) VALUES
    (
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'v1.0.0',
        '{
            "type": "remote_api",
            "endpoint": "https://example.com/api/predict",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "input_schema": {
                "type": "object",
                "properties": {
                    "sequence": {
                        "type": "string",
                        "description": "氨基酸序列",
                        "minLength": 10,
                        "maxLength": 10000
                    },
                    "model": {
                        "type": "string",
                        "enum": ["base", "large", "xl"],
                        "default": "base",
                        "description": "模型大小"
                    }
                },
                "required": ["sequence"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "structure_file": {"type": "string"},
                    "confidence_score": {"type": "number"}
                }
            },
            "gpu_required": true,
            "gpu_memory_mb": 8000,
            "gpu_count": 1,
            "estimated_time_sec": 300,
            "timeout_sec": 600,
            "max_retries": 3,
            "auth_type": "none"
        }'::jsonb,
        '初始版本',
        '00000000-0000-0000-0000-000000000001'
    )
ON CONFLICT (tool_id, version) DO NOTHING;

-- 更新工具的当前版本
UPDATE tools
SET current_version_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
WHERE id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

-- 工具标签关联
INSERT INTO tool_tag_map (tool_id, tag_id) VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111'),  -- AI
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '22222222-2222-2222-2222-222222222222'),  -- Protein
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '55555555-5555-5555-5555-555555555555')   -- Prediction
ON CONFLICT DO NOTHING;

-- 4.2 示例工具2：分子对接
INSERT INTO tools (id, owner_id, name, slug, description, visibility, publish_status) VALUES
    (
        'cccccccc-cccc-cccc-cccc-cccccccccccc',
        '00000000-0000-0000-0000-000000000001',
        'Molecular Docking Tool',
        'molecular-docking-tool',
        '高精度分子对接工具，支持多种对接算法和打分函数。',
        'public',
        'enabled'
    )
ON CONFLICT (slug) DO NOTHING;

INSERT INTO tool_versions (id, tool_id, version, config, notes, created_by) VALUES
    (
        'dddddddd-dddd-dddd-dddd-dddddddddddd',
        'cccccccc-cccc-cccc-cccc-cccccccccccc',
        'v1.0.0',
        '{
            "type": "docker_image",
            "image": "scitool/docking:v1.0.0",
            "command": ["python", "/app/dock.py"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "receptor_file": {"type": "string", "description": "受体文件ID"},
                    "ligand_file": {"type": "string", "description": "配体文件ID"},
                    "center_x": {"type": "number"},
                    "center_y": {"type": "number"},
                    "center_z": {"type": "number"},
                    "box_size": {"type": "number", "default": 20}
                },
                "required": ["receptor_file", "ligand_file"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "docked_poses": {"type": "array"},
                    "binding_affinity": {"type": "number"}
                }
            },
            "gpu_required": false,
            "estimated_time_sec": 120,
            "timeout_sec": 300,
            "max_retries": 2
        }'::jsonb,
        '初始版本',
        '00000000-0000-0000-0000-000000000001'
    )
ON CONFLICT (tool_id, version) DO NOTHING;

UPDATE tools
SET current_version_id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
WHERE id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';

INSERT INTO tool_tag_map (tool_id, tag_id) VALUES
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', '33333333-3333-3333-3333-333333333333'),  -- Molecule
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', '44444444-4444-4444-4444-444444444444')   -- Docking
ON CONFLICT DO NOTHING;

-- =====================================================
-- 5. 示例GPU节点（仅开发环境）
-- =====================================================

INSERT INTO gpu_nodes (id, hostname, gpu_name, gpu_count, total_memory_mb, status, metadata) VALUES
    (
        'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
        'gpu-node-01',
        'NVIDIA RTX 4090',
        2,
        24576,
        'online',
        '{
            "cuda_version": "12.0",
            "driver_version": "535.104.05",
            "compute_capability": "8.9"
        }'::jsonb
    )
ON CONFLICT (hostname) DO NOTHING;

COMMIT;

-- =====================================================
-- 种子数据插入完成
-- =====================================================

-- 验证数据
SELECT '=== 种子数据统计 ===' AS message;
SELECT 'Tags', COUNT(*) FROM tags;
SELECT 'System Config', COUNT(*) FROM system_config;
SELECT 'Users', COUNT(*) FROM users;
SELECT 'Tools', COUNT(*) FROM tools;
SELECT 'Tool Versions', COUNT(*) FROM tool_versions;
SELECT 'GPU Nodes', COUNT(*) FROM gpu_nodes;
