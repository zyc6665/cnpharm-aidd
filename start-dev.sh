#!/bin/bash
# ============================================================================
# SciTool 开发环境启动脚本
# ============================================================================
#
# 功能:
#   - 自动检查并创建 Docker 网络
#   - 构建开发环境镜像
#   - 启动所有服务（后端 + Redis + Celery + Flower）
#   - 显示服务状态和访问地址
#
# 使用方法:
#   ./start-dev.sh              # 交互模式
#   ./start-dev.sh --quick      # 快速启动（跳过所有确认）
#   ./start-dev.sh --rebuild    # 强制重新构建
#   ./start-dev.sh --help       # 显示帮助
#
# ============================================================================

set -e  # 遇到错误立即退出

# 解析命令行参数
QUICK_MODE=false
FORCE_REBUILD=false

for arg in "$@"; do
    case $arg in
        --quick|-q)
            QUICK_MODE=true
            shift
            ;;
        --rebuild|-r)
            FORCE_REBUILD=true
            shift
            ;;
        --help|-h)
            echo "SciTool 开发环境启动脚本"
            echo ""
            echo "用法:"
            echo "  $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --quick, -q      快速启动模式（跳过所有确认）"
            echo "  --rebuild, -r    强制重新构建镜像"
            echo "  --help, -h       显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  $0                # 交互模式启动"
            echo "  $0 --quick        # 快速启动"
            echo "  $0 --rebuild      # 重新构建并启动"
            exit 0
            ;;
        *)
            # 未知参数
            ;;
    esac
done

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_header() {
    echo -e "${BLUE}============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 检查 Docker
check_docker() {
    print_header "检查 Docker 环境"

    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        print_error "Docker 服务未运行，请启动 Docker"
        exit 1
    fi

    print_success "Docker 环境正常"
}

# 检查 docker-compose
check_compose() {
    # 检查是否支持 docker compose (v2) 或 docker-compose (v1)
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
        print_success "检测到 Docker Compose v2"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
        print_success "检测到 Docker Compose v1"
    else
        print_error "Docker Compose 未安装"
        print_info "请安装 Docker Compose:"
        print_info "  - v2 (推荐): 随 Docker Desktop 自动安装"
        print_info "  - v1: pip install docker-compose"
        exit 1
    fi
}

# 创建网络
create_network() {
    print_header "检查 Docker 网络"

    if docker network inspect cpumodel &> /dev/null; then
        print_success "网络 cpumodel 已存在"
    else
        print_info "创建网络 cpumodel..."
        docker network create cpumodel
        print_success "网络 cpumodel 创建成功"
    fi
}

# 清理旧容器（可选）
cleanup_old_containers() {
    print_header "清理旧容器（可选）"

    # 快速模式直接跳过
    if [ "$QUICK_MODE" = true ]; then
        print_info "快速模式：跳过容器清理"
        return
    fi

    read -p "是否停止并删除旧容器？(y/N): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "停止旧容器..."
        $COMPOSE_CMD down 2>/dev/null || true
        print_success "旧容器已清理"
    else
        print_info "跳过清理"
    fi
}

# 构建镜像
build_images() {
    print_header "检查镜像状态"

    # 强制重建模式
    if [ "$FORCE_REBUILD" = true ]; then
        print_info "强制重建模式：开始重新构建后端镜像..."
        $COMPOSE_CMD build --no-cache backend
        print_success "镜像重新构建完成"
        return
    fi

    # 检查镜像是否存在
    if docker images | grep -q "scitool-backend.*dev"; then
        print_success "检测到已存在的开发镜像"

        # 快速模式直接跳过
        if [ "$QUICK_MODE" = true ]; then
            print_info "快速模式：使用现有镜像"
            return
        fi

        # 询问是否重新构建
        echo ""
        read -p "是否重新构建镜像？(y/N): " -n 1 -r
        echo

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "开始重新构建后端镜像..."
            $COMPOSE_CMD build backend
            print_success "镜像重新构建完成"
        else
            print_info "跳过构建，使用现有镜像"
        fi
    else
        print_info "未检测到开发镜像，开始构建..."
        $COMPOSE_CMD build backend
        print_success "镜像构建完成"
    fi
}

# 启动服务
start_services() {
    print_header "启动服务"

    print_info "启动 Redis..."
    $COMPOSE_CMD up -d redis

    # 等待 Redis 健康
    print_info "等待 Redis 就绪..."
    sleep 5

    print_info "启动后端服务..."
    $COMPOSE_CMD up -d backend

    print_info "启动 Celery Worker..."
    $COMPOSE_CMD up -d celery-worker

    print_info "启动 Flower 监控..."
    $COMPOSE_CMD up -d flower

    print_success "所有服务已启动"
}

# 检查服务状态
check_services() {
    print_header "服务状态检查"

    sleep 3  # 等待服务启动

    # 显示运行中的容器
    $COMPOSE_CMD ps

    echo ""
    print_info "检查服务健康状态..."

    # 检查 Redis
    if $COMPOSE_CMD exec -T redis redis-cli -a scitool123 ping &> /dev/null; then
        print_success "Redis 运行正常"
    else
        print_warning "Redis 连接失败"
    fi

    # 检查后端
    sleep 5  # 等待后端启动
    if curl -f http://localhost:8000/api/v1/system/health &> /dev/null; then
        print_success "后端 API 运行正常"
    else
        print_warning "后端 API 尚未就绪（可能还在启动中）"
    fi
}

# 显示访问信息
show_info() {
    print_header "🚀 开发环境已就绪！"

    echo -e "${GREEN}"
    echo "📡 服务访问地址:"
    echo "   - 后端 API:      http://localhost:8000"
    echo "   - API 文档:      http://localhost:8000/docs"
    echo "   - API Redoc:     http://localhost:8000/redoc"
    echo "   - Flower 监控:   http://localhost:9555 (admin/scitool123)"
    echo "   - Redis:         localhost:9500 (password: scitool123)"
    echo ""
    echo "📝 常用命令:"
    if [[ "$COMPOSE_CMD" == "docker compose" ]]; then
        echo "   - 查看后端日志:     docker compose logs -f backend"
        echo "   - 查看 Worker 日志:  docker compose logs -f celery-worker"
        echo "   - 重启后端:         docker compose restart backend"
        echo "   - 停止所有服务:     docker compose down"
        echo "   - 进入后端容器:     docker compose exec backend bash"
    else
        echo "   - 查看后端日志:     docker-compose logs -f backend"
        echo "   - 查看 Worker 日志:  docker-compose logs -f celery-worker"
        echo "   - 重启后端:         docker-compose restart backend"
        echo "   - 停止所有服务:     docker-compose down"
        echo "   - 进入后端容器:     docker-compose exec backend bash"
    fi
    echo ""
    echo "🔥 热重载已启用:"
    echo "   - 修改 backend/app/ 下的代码会自动重载后端"
    echo "   - 修改 backend/app/ 下的代码会自动重载 Celery Worker"
    echo "   - 无需手动重启服务！"
    echo ""
    echo "🧪 测试 API:"
    echo "   curl http://localhost:8000/api/v1/system/health"
    echo -e "${NC}"
}

# 主流程
main() {
    clear
    print_header "SciTool 开发环境启动器"

    # 1. 检查环境
    check_docker
    check_compose

    # 2. 创建网络
    create_network

    # 3. 清理旧容器（可选）
    cleanup_old_containers

    # 4. 构建镜像
    build_images

    # 5. 启动服务
    start_services

    # 6. 检查状态
    check_services

    # 7. 显示信息
    show_info

    # 8. 尾随日志（可选）
    echo ""

    # 快速模式不查看日志
    if [ "$QUICK_MODE" = true ]; then
        print_info "快速模式：跳过日志查看"
        print_info "使用以下命令查看日志："
        if [[ "$COMPOSE_CMD" == "docker compose" ]]; then
            echo "  docker compose logs -f backend"
        else
            echo "  docker-compose logs -f backend"
        fi
        return
    fi

    read -p "是否查看后端实时日志？(Y/n): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo ""
        print_info "按 Ctrl+C 退出日志查看"
        sleep 2
        $COMPOSE_CMD logs -f backend
    fi
}

# 执行主流程
main
