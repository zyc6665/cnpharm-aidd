#!/bin/bash
# ============================================================================
# SciTool Celery + Redis 快速启动脚本
# ============================================================================

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 标题
echo "============================================================================"
echo -e "${GREEN}SciTool - Celery 任务队列启动脚本${NC}"
echo "============================================================================"
echo ""

# 1. 检查Docker
print_info "检查Docker环境..."
if ! command -v docker &> /dev/null; then
    print_error "Docker未安装，请先安装Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

print_success "Docker环境检查通过"
echo ""

# 2. 检查网络
print_info "检查cpumodel网络..."
if ! docker network inspect cpumodel &> /dev/null; then
    print_warning "cpumodel网络不存在，正在创建..."
    docker network create cpumodel
    print_success "cpumodel网络创建成功"
else
    print_success "cpumodel网络已存在"
fi
echo ""

# 3. 构建镜像（首次运行需要）
if [ "$1" == "--build" ]; then
    print_info "正在构建Docker镜像..."
    docker-compose -f docker-compose.celery.yml build --no-cache
    print_success "镜像构建完成"
    echo ""
fi

# 4. 启动服务
print_info "启动Celery + Redis服务..."
docker-compose -f docker-compose.celery.yml up -d

echo ""
print_info "等待服务启动..."
sleep 5

# 5. 检查服务状态
echo ""
print_info "检查服务状态..."
echo ""
docker-compose -f docker-compose.celery.yml ps

# 6. 验证Redis连接
echo ""
print_info "验证Redis连接..."
if docker-compose -f docker-compose.celery.yml exec -T redis redis-cli -a scitool123 ping &> /dev/null; then
    print_success "Redis连接正常"
else
    print_error "Redis连接失败"
fi

# 7. 检查Celery Worker
echo ""
print_info "检查Celery Worker状态..."
sleep 3
if docker-compose -f docker-compose.celery.yml exec -T celery-worker \
    celery -A app.celery_app.celery_app inspect ping &> /dev/null; then
    print_success "Celery Worker运行正常"
else
    print_warning "Celery Worker可能尚未就绪，请稍后查看日志"
fi

# 8. 显示访问信息
echo ""
echo "============================================================================"
print_success "服务启动完成！"
echo "============================================================================"
echo ""
echo -e "${BLUE}访问信息:${NC}"
echo "  - Flower监控面板: http://localhost:9555"
echo "    登录账号: admin"
echo "    登录密码: scitool123"
echo ""
echo -e "${BLUE}常用命令:${NC}"
echo "  - 查看日志: docker-compose -f docker-compose.celery.yml logs -f"
echo "  - 停止服务: docker-compose -f docker-compose.celery.yml down"
echo "  - 重启服务: docker-compose -f docker-compose.celery.yml restart"
echo "  - 查看状态: docker-compose -f docker-compose.celery.yml ps"
echo ""
echo -e "${BLUE}Celery管理命令:${NC}"
echo "  - 查看活跃任务:"
echo "    docker-compose -f docker-compose.celery.yml exec celery-worker \\"
echo "      celery -A app.celery_app.celery_app inspect active"
echo ""
echo -e "${BLUE}详细文档:${NC}"
echo "  - 查看完整部署文档: cat document/CELERY_DEPLOYMENT.md"
echo ""
echo "============================================================================"
