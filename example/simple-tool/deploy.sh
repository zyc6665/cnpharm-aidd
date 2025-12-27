#!/bin/bash
# Simple Text Tool 部署脚本

set -e

echo "=========================================="
echo "Simple Text Tool - 部署脚本"
echo "=========================================="
echo ""

# 检查 Docker 网络
echo "📡 检查 Docker 网络..."
if ! docker network inspect cpumodel >/dev/null 2>&1; then
    echo "❌ 网络 cpumodel 不存在，正在创建..."
    docker network create cpumodel
    echo "✅ 网络创建成功"
else
    echo "✅ 网络已存在"
fi
echo ""

# 停止旧容器
echo "🛑 停止旧容器..."
docker compose down 2>/dev/null || true
echo ""

# 构建镜像
echo "🔨 构建 Docker 镜像..."
docker compose build
echo ""

# 启动服务
echo "🚀 启动服务..."
docker compose up -d
echo ""

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5
echo ""

# 检查服务状态
echo "🔍 检查服务状态..."
if docker ps | grep -q simple-text-tool; then
    echo "✅ 容器运行正常"
else
    echo "❌ 容器未运行"
    exit 1
fi
echo ""
# 测试健康检查
echo "🏥 测试健康检查..."
if curl -s http://localhost:8100/health | grep -q "healthy"; then
    echo "✅ 健康检查通过"
else
    echo "❌ 健康检查失败"
    docker logs simple-text-tool
    exit 1
fi
echo ""

# 测试 API
echo "🧪 测试 API..."
response=$(curl -s -X POST http://localhost:8100/process \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-001",
    "params": {
      "text": "Hello World",
      "operation": "uppercase",
      "add_stats": true
    }
  }')

if echo "$response" | grep -q "HELLO WORLD"; then
    echo "✅ API 测试通过"
    echo "响应: $response"
else
    echo "❌ API 测试失败"
    echo "响应: $response"
    exit 1
fi
echo ""

echo "=========================================="
echo "✅ 部署成功！"
echo "=========================================="
echo ""
echo "服务信息："
echo "  - 容器名称: simple-text-tool"
echo "  - 访问地址: http://localhost:8100"
echo "  - 健康检查: http://localhost:8100/health"
echo "  - API 文档: http://localhost:8100/docs"
echo ""
echo "查看日志: docker logs -f simple-text-tool"
echo "停止服务: docker-compose down"
echo ""
