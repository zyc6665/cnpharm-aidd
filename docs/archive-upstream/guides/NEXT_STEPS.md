# LVPocket工具部署 - 下一步操作

**当前状态**: ✅ 配置完成，准备部署测试

---

## 🚀 快速开始（3步完成）

### 1️⃣ 启动LVPocket服务

```bash
cd /data/zhouyc/cpumodel_sciminer/example/lvpocket-service
docker-compose up -d --build

# 等待启动完成（60-120秒），查看日志
docker-compose logs -f
```

**成功标志**: 日志显示 `"模型加载成功"` 和 `"Application startup complete"`

### 2️⃣ 验证服务

```bash
# 检查健康状态
curl http://localhost:8000/api/v1/health | jq

# 应返回: {"status": "healthy", "model_loaded": true, "gpu_available": true}
```

### 3️⃣ 创建并测试工具

```bash
cd /data/zhouyc/cpumodel_sciminer

# 一键创建并测试
python scripts/create_tool.py \
  --config lvpocket_tool_config.json \
  --test \
  --test-params lvpocket_test_params.json
```

---

## 📁 相关文件

| 文件 | 用途 | 位置 |
|------|------|------|
| lvpocket_tool_config.json | 工具配置 | 项目根目录 |
| lvpocket_test_params.json | 测试参数 | 项目根目录 |
| LVPOCKET_DEPLOY.md | 详细部署指南 | 项目根目录 |
| CREATE_TOOL_GUIDE.md | 工具创建通用指南 | 项目根目录 |
| deploy/compose/docker-compose.dev.yml | 服务部署配置 | example/lvpocket-service/ |
| .env | 环境变量 | example/lvpocket-service/ |
| config.py (已修改) | 模型路径配置 | example/lvpocket-service/app/ |

---

## ✅ 已完成的配置

- [x] 工具配置JSON - 定义API端点和Schema
- [x] 测试参数JSON - 使用1A28.pdb测试
- [x] 模型路径适配 - config.py指向实际的.hdf文件
- [x] 环境变量配置 - .env文件包含所有必需配置
- [x] 部署文档 - 完整的部署和故障排查指南

---

## 🎯 预期结果

**工具创建成功后**：
- 工具名称: `LVPocket蛋白质口袋预测`
- 工具Slug: `lvpocket-predict`
- 支持的结构分类: baseline / alpha / beta / alpha_beta / alpha_plus_beta
- 输入: PDB/MOL2蛋白质文件
- 输出: JSON格式的口袋预测结果（包含坐标、分数、体积等）

**测试任务成功后**：
- 任务状态: SUCCESS
- 预测到的口袋数量: 3-5个
- 处理时间: 10-20秒
- 输出文件: JSON格式的口袋详情

---

## ⚠️ 常见问题

### Q1: 容器启动失败
**检查**: GPU是否可用 (`nvidia-smi`)
**解决**: 确保安装了NVIDIA Container Toolkit

### Q2: 健康检查失败
**检查**: `docker-compose logs` 查看错误
**解决**: 通常是模型加载问题，等待更长时间或检查模型文件是否存在

### Q3: 工具测试失败
**检查**: lvpocket-service是否加入了cpumodel-net网络
**解决**: `docker network connect cpumodel-net lvpocket-service`

---

**准备好了吗？** 现在可以执行步骤1开始部署！

如需详细说明，请查看 `LVPOCKET_DEPLOY.md`
