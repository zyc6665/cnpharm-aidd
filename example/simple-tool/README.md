# Simple Text Tool - 简单文本处理工具

一个用于测试 SciTool 平台集成的简单文本处理工具。

## 功能特性

- ✅ 文本大小写转换
- ✅ 文本反转
- ✅ 文本统计（字符数、单词数、行数）
- ✅ 标准 JSON API 接口
- ✅ Docker 容器化部署
- ✅ 健康检查端点

## 快速开始

### 1. 构建和启动服务

```bash
cd /data/zhouyc/cpumodel_sciminer/example/simple-tool
docker-compose up -d --build
```

### 2. 验证服务状态

```bash
# 检查容器状态
docker ps | grep simple-text-tool

# 测试健康检查
curl http://localhost:9502/health
```

### 3. 测试 API

```bash
curl -X POST http://localhost:9502/process \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-001",
    "params": {
      "text": "Hello World",
      "operation": "uppercase",
      "add_stats": true
    }
  }'
```

## API 文档

### 健康检查

**端点**: `GET /health`

**响应示例**:
```json
{
  "status": "healthy",
  "service": "simple-text-tool",
  "version": "1.0.0"
}
```

### 文本处理

**端点**: `POST /process`

**请求参数**:
```json
{
  "task_id": "string (必填)",
  "params": {
    "text": "string (必填) - 要处理的文本",
    "operation": "string (必填) - uppercase|lowercase|reverse|stats",
    "add_stats": "boolean (可选) - 是否添加统计信息，默认false"
  },
  "input_files": {}
}
```

**响应示例**:
```json
{
  "success": true,
  "task_id": "test-001",
  "result": {
    "processed_text": "HELLO WORLD",
    "operation": "uppercase",
    "statistics": {
      "char_count": 11,
      "word_count": 2,
      "line_count": 1
    }
  },
  "error": null
}
```

## 支持的操作

| 操作 | 说明 | 示例输入 | 示例输出 |
|------|------|----------|----------|
| `uppercase` | 转换为大写 | "hello" | "HELLO" |
| `lowercase` | 转换为小写 | "HELLO" | "hello" |
| `reverse` | 反转文本 | "hello" | "olleh" |
| `stats` | 仅统计信息 | "hello world" | 原文 + 统计 |

## 集成到 SciTool 平台

### 1. 注册工具到平台

使用 `tool_config.json` 配置文件注册工具：

```bash
cd /data/zhouyc/cpumodel_sciminer/backend
python3 ../create_tool.py --config ../example/simple-tool/tool_config.json
```

### 2. 测试工具调用

通过平台 API 或 Celery 任务队列调用工具。

## 故障排除

### 容器无法启动

```bash
# 查看日志
docker logs simple-text-tool

# 检查端口占用
netstat -tlnp | grep 9502
```

### API 调用失败

```bash
# 检查服务健康状态
curl http://localhost:9502/health

# 查看容器网络
docker network inspect cpumodel-net
```

## 技术栈

- **FastAPI**: 现代高性能 Web 框架
- **Pydantic**: 数据验证和序列化
- **Uvicorn**: ASGI 服务器
- **Docker**: 容器化部署

## 许可证

MIT License
