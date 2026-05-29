# LVPocket工具部署指南

本指南用于将LVPocket蛋白质口袋预测服务部署到SciTool平台。

---

## 📋 部署前准备

### 1. 检查模型文件

LVPocket需要预训练模型文件才能运行。检查模型是否存在：

```bash
ls -lh example/lvpocket-service/model/LVpocket/trained_model/
```

**必需的模型文件**：
- `scale_0.5_1.h5` - 基线模型（必需）
- `scale_0.5_1_a.h5` - α螺旋模型（可选）
- `scale_0.5_1_b.h5` - β折叠模型（可选）
- `scale_0.5_1_ab.h5` - α/β交替模型（可选）
- `scale_0.5_1_apb.h5` - α+β分离模型（可选）

**下载模型**（如果不存在）：
```bash
# 从 Zenodo 下载
wget https://zenodo.org/record/10633690/files/scale_0.5_1.h5 \
  -O example/lvpocket-service/model/LVpocket/trained_model/scale_0.5_1.h5
```

### 2. 检查GPU支持

LVPocket需要GPU加速，确认系统已安装NVIDIA Container Toolkit：

```bash
# 检查GPU
nvidia-smi

# 检查Docker GPU支持
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### 3. 检查网络配置

LVPocket服务需要加入 `cpumodel-net` 网络以便后端容器访问：

```bash
# 检查网络是否存在
docker network ls | grep cpumodel-net

# 如果不存在，创建网络（通常启动后端时已创建）
docker network create cpumodel-net
```

---

## 🚀 部署步骤

### 步骤1: 进入服务目录

```bash
cd /data/zhouyc/cpumodel_sciminer/example/lvpocket-service
```

### 步骤2: 构建并启动服务

**首次启动**（需要构建镜像）：
```bash
docker-compose up -d --build
```

**后续启动**（镜像已存在）：
```bash
docker-compose up -d
```

### 步骤3: 查看启动日志

```bash
# 查看启动日志
docker-compose logs -f

# 等待模型加载完成，出现类似信息：
# "Model loaded successfully"
# "Application startup complete"
```

**预期启动时间**：60-120秒（包含模型加载）

### 步骤4: 验证服务健康状态

```bash
# 方法1: 使用健康检查端点
curl http://localhost:8000/api/v1/health

# 预期响应：
# {
#   "status": "healthy",
#   "model_loaded": true,
#   "gpu_available": true,
#   ...
# }

# 方法2: 检查Docker健康状态
docker ps | grep lvpocket-service
# STATUS列应显示 "healthy"
```

---

## 🧪 测试API

### 测试1: 健康检查

```bash
curl http://localhost:8000/api/v1/health | jq
```

### 测试2: 模型信息

```bash
curl http://localhost:8000/api/v1/model/info | jq
```

### 测试3: 简单预测（使用示例PDB文件）

```bash
# 创建测试请求
cat > test_request.json << 'EOF'
{
  "params": {
    "threshold": 0.5,
    "min_size": 50,
    "output_formats": ["json"],
    "structure_class": "baseline"
  },
  "input_files": {
    "protein_file": "https://files.rcsb.org/download/1A28.pdb"
  }
}
EOF

# 发送预测请求
curl -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d @test_request.json | jq

# 预期响应包含：
# - success: true
# - result.num_pockets: 口袋数量
# - result.pockets: 口袋详情数组
```

---

## 🔧 在SciTool平台中创建工具

### 步骤1: 创建工具记录

使用已准备好的配置文件：

```bash
cd /data/zhouyc/cpumodel_sciminer

# 创建工具（仅创建，不测试）
python create_tool.py --config lvpocket_tool_config.json
```

**成功输出示例**：
```
✅ 工具创建成功: LVPocket蛋白质口袋预测 (ID: xxx-xxx-xxx)
✅ 工具版本创建成功: 1.0.0 (ID: yyy-yyy-yyy)

工具信息:
  名称: LVPocket蛋白质口袋预测
  Slug: lvpocket-predict
  ID: xxx-xxx-xxx
  版本ID: yyy-yyy-yyy
  类型: remote_api
```

### 步骤2: 测试工具集成

**重要**：在测试前确保 lvpocket-service 容器正在运行且健康状态为 healthy。

```bash
# 创建并测试
python create_tool.py \
  --config lvpocket_tool_config.json \
  --test \
  --test-params lvpocket_test_params.json
```

**预期测试输出**：
```
🧪 测试任务创建成功: task-xxx-xxx
   工具: LVPocket蛋白质口袋预测
   版本: 1.0.0
   参数: {...}

⏳ 开始执行任务...

✅ 任务执行成功!
   结果: {
     "success": true,
     "result": {
       "protein_name": "1A28",
       "num_pockets": 3,
       "processing_time": 12.45,
       ...
     }
   }
```

---

## 📊 验证清单

完成部署后，验证以下项目：

- [ ] LVPocket服务容器正在运行
- [ ] 容器健康状态为 `healthy`
- [ ] GPU正常识别（`/health` 接口 `gpu_available: true`）
- [ ] 模型已加载（`/health` 接口 `model_loaded: true`）
- [ ] API测试通过（`/predict` 接口返回预测结果）
- [ ] SciTool工具记录创建成功
- [ ] SciTool工具测试通过（任务状态为 SUCCESS）

---

## 🐛 故障排查

### 问题1: 容器无法启动

**症状**：`docker-compose up` 失败

**检查**：
```bash
# 查看详细错误
docker-compose logs

# 常见原因：
# 1. 模型文件不存在
# 2. GPU不可用
# 3. 端口被占用
```

**解决方法**：
- 确认模型文件存在
- 检查 `nvidia-smi` 输出
- 修改端口映射（如改为 `9000:8000`）

### 问题2: 健康检查失败

**症状**：容器运行但健康状态为 `unhealthy`

**检查**：
```bash
# 查看启动日志
docker-compose logs -f | grep -i error

# 手动测试健康端点
curl http://localhost:8000/api/v1/health
```

**常见原因**：
- 模型加载失败（文件损坏或路径错误）
- GPU内存不足
- TensorFlow版本不兼容

**解决方法**：
```bash
# 重新下载模型
rm model/LVpocket/trained_model/scale_0.5_1.h5
wget https://zenodo.org/record/10633690/files/scale_0.5_1.h5 \
  -O model/LVpocket/trained_model/scale_0.5_1.h5

# 增加启动等待时间
# 编辑 docker-compose.yml:
# healthcheck.start_period: 120s
```

### 问题3: 预测请求失败

**症状**：API返回500错误或超时

**检查**：
```bash
# 查看容器日志
docker-compose logs -f | grep -i predict

# 查看容器资源使用
docker stats lvpocket-service
```

**常见原因**：
- 输入文件格式不正确（非PDB/MOL2）
- GPU内存不足
- 超时设置过短

**解决方法**：
- 验证输入文件：`curl -I https://files.rcsb.org/download/1A28.pdb`
- 减少并发请求
- 增加超时：环境变量 `REQUEST_TIMEOUT=600`

### 问题4: SciTool工具测试失败

**症状**：`create_tool.py --test` 报错

**检查**：
```bash
# 1. 确认服务可访问
curl http://lvpocket-service:8000/api/v1/health

# 2. 检查网络连接
docker network inspect cpumodel-net | grep lvpocket
docker network inspect cpumodel-net | grep backend

# 3. 查看任务执行日志
# 在数据库中查询任务状态
```

**常见原因**：
- 服务未加入 `cpumodel-net` 网络
- 后端容器无法解析 `lvpocket-service` 域名
- 端点URL配置错误

**解决方法**：
```bash
# 确保docker-compose.yml包含正确的网络配置
# networks:
#   - cpumodel-net

# 手动添加到网络
docker network connect cpumodel-net lvpocket-service

# 从后端容器测试连接
docker exec scitool-backend curl http://lvpocket-service:8000/api/v1/health
```

---

## 📝 配置说明

### 工具配置文件：lvpocket_tool_config.json

**关键字段**：

| 字段 | 值 | 说明 |
|------|------|------|
| endpoint | http://lvpocket-service:8000/predict | 容器内部服务地址 |
| method | POST | HTTP方法 |
| timeout_sec | 300 | 超时5分钟（模型推理需要时间） |
| input_schema.params.threshold | 0-1 | 口袋预测阈值，越高越严格 |
| input_schema.params.structure_class | baseline/alpha/beta/... | SCOP结构分类选择 |

### 测试参数文件：lvpocket_test_params.json

**默认使用**：
- `threshold: 0.5` - 中等严格度
- `structure_class: baseline` - 通用模型
- `protein_file: 1A28.pdb` - RCSB PDB公开结构

**修改测试蛋白质**：
```json
{
  "params": { ... },
  "input_files": {
    "protein_file": "https://files.rcsb.org/download/YOUR_PDB.pdb"
  }
}
```

---

## 🔄 服务管理

### 启动/停止

```bash
cd /data/zhouyc/cpumodel_sciminer/example/lvpocket-service

# 启动
docker-compose up -d

# 停止
docker-compose down

# 重启
docker-compose restart

# 查看状态
docker-compose ps
```

### 查看日志

```bash
# 实时日志
docker-compose logs -f

# 最近100行
docker-compose logs --tail=100

# 特定时间范围
docker-compose logs --since 30m
```

### 进入容器调试

```bash
# 进入bash
docker-compose exec lvpocket-service bash

# 查看Python环境
docker-compose exec lvpocket-service python --version
docker-compose exec lvpocket-service pip list

# 测试模型加载
docker-compose exec lvpocket-service python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

---

## 📚 参考文档

- **LVPocket论文**: [doi.org/10.5281/zenodo.10633690](https://doi.org/10.5281/zenodo.10633690)
- **API文档**: http://localhost:8000/docs（启动后访问）
- **Docker Compose文档**: https://docs.docker.com/compose/
- **NVIDIA Container Toolkit**: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/

---

**部署完成后，工具将在SciTool平台的工具列表中可用，用户可以通过API提交预测任务！**
