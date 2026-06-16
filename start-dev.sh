#!/bin/bash
# ============================================================================
# SciTool 容器内开发环境启动脚本
# ============================================================================
#
# 功能:
#   - 启动后端 FastAPI 开发服务
#   - 启动前端 Vite 开发服务
#   - 退出时清理前后端子进程
#
# 使用方法:
#   ./start-dev.sh              # 启动前后端并等待
#   ./start-dev.sh --quick      # 兼容旧参数，行为等同默认启动
#   ./start-dev.sh --help       # 显示帮助
#
# ============================================================================

set -euo pipefail

QUICK_MODE=false
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8585}"
BACKEND_PID=""
FRONTEND_PID=""

for arg in "$@"; do
    case "$arg" in
        --quick|-q)
            QUICK_MODE=true
            ;;
        --help|-h)
            echo "SciTool 容器内开发环境启动脚本"
            echo ""
            echo "用法:"
            echo "  $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --quick, -q      兼容旧参数，行为等同默认启动"
            echo "  --help, -h       显示此帮助信息"
            echo ""
            echo "环境变量:"
            echo "  BACKEND_PORT     后端端口，默认 8000"
            echo "  FRONTEND_PORT    前端端口，默认 8585"
            exit 0
            ;;
        *)
            echo "未知参数: $arg"
            echo "使用 $0 --help 查看帮助"
            exit 1
            ;;
    esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

command_exists() {
    command -v "$1" > /dev/null 2>&1
}

check_environment() {
    print_header "检查本地开发环境"

    if [ ! -d "${BACKEND_DIR}" ]; then
        print_error "后端目录不存在: ${BACKEND_DIR}"
        exit 1
    fi

    if [ ! -d "${FRONTEND_DIR}" ]; then
        print_error "前端目录不存在: ${FRONTEND_DIR}"
        exit 1
    fi

    if ! command_exists python; then
        print_error "未找到 python 命令"
        exit 1
    fi

    if ! command_exists npm; then
        print_error "未找到 npm 命令"
        exit 1
    fi

    print_success "本地开发环境检查通过"
}

ensure_frontend_dependencies() {
    if [ -d "${FRONTEND_DIR}/node_modules" ]; then
        return
    fi

    print_warning "未检测到 frontend/node_modules"
    print_info "请先在 frontend 目录执行 npm install"
    exit 1
}

start_backend() {
    print_header "启动后端服务"
    print_info "后端监听: http://localhost:${BACKEND_PORT}"

    (
        cd "${BACKEND_DIR}"
        exec python -m uvicorn app.main:app \
            --host 0.0.0.0 \
            --port "${BACKEND_PORT}" \
            --reload
    ) &
    BACKEND_PID=$!

    print_success "后端进程已启动，PID: ${BACKEND_PID}"
}

start_frontend() {
    print_header "启动前端服务"
    print_info "前端监听: http://localhost:${FRONTEND_PORT}"

    (
        cd "${FRONTEND_DIR}"
        exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}"
    ) &
    FRONTEND_PID=$!

    print_success "前端进程已启动，PID: ${FRONTEND_PID}"
}

stop_services() {
    echo ""
    print_info "正在停止开发服务..."

    if [ -n "${FRONTEND_PID}" ] && kill -0 "${FRONTEND_PID}" > /dev/null 2>&1; then
        kill "${FRONTEND_PID}" > /dev/null 2>&1 || true
    fi

    if [ -n "${BACKEND_PID}" ] && kill -0 "${BACKEND_PID}" > /dev/null 2>&1; then
        kill "${BACKEND_PID}" > /dev/null 2>&1 || true
    fi

    wait "${FRONTEND_PID}" > /dev/null 2>&1 || true
    wait "${BACKEND_PID}" > /dev/null 2>&1 || true

    print_success "开发服务已停止"
}

check_services() {
    print_header "服务状态检查"

    sleep 3

    if kill -0 "${BACKEND_PID}" > /dev/null 2>&1; then
        print_success "后端进程运行中"
    else
        print_error "后端进程已退出"
        exit 1
    fi

    if kill -0 "${FRONTEND_PID}" > /dev/null 2>&1; then
        print_success "前端进程运行中"
    else
        print_error "前端进程已退出"
        exit 1
    fi

    if command_exists curl; then
        if curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/system/health" > /dev/null 2>&1; then
            print_success "后端 API 健康检查通过"
        else
            print_warning "后端 API 尚未就绪，可稍后访问健康检查接口"
        fi
    else
        print_warning "未找到 curl，跳过健康检查"
    fi
}

show_info() {
    print_header "开发服务已启动"

    echo -e "${GREEN}"
    echo "服务访问地址:"
    echo "   - 前端页面:      http://localhost:${FRONTEND_PORT}"
    echo "   - 后端 API:      http://localhost:${BACKEND_PORT}"
    echo "   - API 文档:      http://localhost:${BACKEND_PORT}/docs"
    echo "   - API Redoc:     http://localhost:${BACKEND_PORT}/redoc"
    echo ""
    echo "热重载:"
    echo "   - 修改 backend/app/ 下的代码会自动重载后端"
    echo "   - 修改 frontend/src/ 下的代码会自动热更新前端"
    echo ""
    echo "测试 API:"
    echo "   curl http://localhost:${BACKEND_PORT}/api/v1/system/health"
    echo -e "${NC}"
}

wait_for_processes() {
    if [ "${QUICK_MODE}" = true ]; then
        print_info "快速模式参数已保留兼容；本地进程模式下脚本会保持前台运行"
    fi

    print_info "按 Ctrl+C 停止前后端服务"
    wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
}

main() {
    clear
    print_header "SciTool 容器内开发环境启动器"

    trap stop_services EXIT INT TERM

    check_environment
    ensure_frontend_dependencies
    start_backend
    start_frontend
    check_services
    show_info
    wait_for_processes
}

main
