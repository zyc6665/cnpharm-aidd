#!/bin/bash
# ============================================================================
# LVPocket Service Docker 启动脚本
# ============================================================================
#
# 使用方法:
#   1. 添加执行权限: chmod +x docker-run.sh
#   2. 构建镜像:     ./docker-run.sh build
#   3. 启动容器:     ./docker-run.sh start
#   4. 停止容器:     ./docker-run.sh stop
#   5. 查看日志:     ./docker-run.sh logs
#   6. 进入容器:     ./docker-run.sh exec
#   7. 重启容器:     ./docker-run.sh restart
#   8. 查看状态:     ./docker-run.sh status
#   9. 清理:         ./docker-run.sh clean
#
# ============================================================================

# ==================== 配置区域（可根据需要修改） ====================

# 镜像名称和标签
IMAGE_NAME="lvpocket-service"
IMAGE_TAG="1.0.0"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

# 容器名称
CONTAINER_NAME="lvpocket-service"

# 端口映射（主机端口:容器端口）
HOST_PORT=8000
CONTAINER_PORT=8000

# GPU 配置
# 可选值: "all" | "0" | "1" | "0,1" | "none"(不使用GPU)
GPU_DEVICE="all"

# 获取脚本所在目录（用于挂载卷）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 数据卷挂载路径
MODEL_DIR="${SCRIPT_DIR}/model"
INPUT_DIR="${SCRIPT_DIR}/data/input"
OUTPUT_DIR="${SCRIPT_DIR}/data/output"

# ==================== 环境变量配置 ====================

# 服务配置
APP_NAME="LVPocket Service"
APP_VERSION="1.0.0"
LOG_LEVEL="INFO"
HOST="0.0.0.0"
PORT="8000"
WORKERS="1"

# LVpocket 源码路径（容器内路径）
LVPOCKET_SOURCE_PATH="/app/model/LVpocket"

# 模型配置
MODEL_DIR="/app/model/LVpocket/trained_model"
MODEL_PATH="/app/model/LVpocket/trained_model/scale_0.5_1.h5"
MODEL_VERSION="1.0.0"
SCALE="0.5"
MAX_DIST="35.0"

# SCOP 结构分类配置
# 可选值: baseline | alpha | beta | alpha_beta | alpha_plus_beta
DEFAULT_STRUCTURE_CLASS="baseline"

# 预测参数
DEFAULT_THRESHOLD="0.5"
DEFAULT_MIN_SIZE="50"

# 文件配置
MAX_FILE_SIZE="52428800"
REQUEST_TIMEOUT="300"

# GPU/TensorFlow 配置
CUDA_VISIBLE_DEVICES="0"
TF_FORCE_GPU_ALLOW_GROWTH="true"
TF_CPP_MIN_LOG_LEVEL="2"

# ==================== 颜色输出 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_title() {
    echo -e "${BLUE}========== $1 ==========${NC}"
}

# ==================== 函数定义 ====================

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
}

# 检查 NVIDIA Docker 支持
check_nvidia_docker() {
    if [ "$GPU_DEVICE" != "none" ]; then
        if ! docker info 2>/dev/null | grep -q "Runtimes.*nvidia"; then
            log_warn "NVIDIA Container Toolkit 可能未安装，GPU 支持可能不可用"
            log_warn "安装指南: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        fi
    fi
}

# 检查必要目录和文件
check_prerequisites() {
    log_info "检查必要目录和文件..."

    # 检查 model 目录
    if [ ! -d "$MODEL_DIR" ]; then
        log_error "模型目录不存在: $MODEL_DIR"
        exit 1
    fi

    # 检查 LVpocket 源码
    if [ ! -d "$MODEL_DIR/LVpocket" ]; then
        log_error "LVpocket 源码目录不存在: $MODEL_DIR/LVpocket"
        exit 1
    fi

    # 检查模型文件（警告但不退出）
    if [ ! -f "$MODEL_DIR/LVpocket/trained_model/scale_0.5_1.h5" ]; then
        log_warn "模型文件不存在: $MODEL_DIR/LVpocket/trained_model/scale_0.5_1.h5"
        log_warn "请从 Zenodo 下载: https://doi.org/10.5281/zenodo.10633690"
    fi

    # 创建数据目录
    mkdir -p "$INPUT_DIR" "$OUTPUT_DIR"
    log_info "数据目录已创建"
}

# 构建镜像
build_image() {
    log_title "构建 Docker 镜像"
    check_docker
    check_prerequisites

    log_info "开始构建镜像: $FULL_IMAGE"
    docker build -t "$FULL_IMAGE" "$SCRIPT_DIR"

    if [ $? -eq 0 ]; then
        log_info "镜像构建成功: $FULL_IMAGE"
    else
        log_error "镜像构建失败"
        exit 1
    fi
}

# 启动容器
start_container() {
    log_title "启动容器"
    check_docker
    check_nvidia_docker
    check_prerequisites

    # 检查容器是否已存在
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_warn "容器已存在: $CONTAINER_NAME"

        # 检查是否正在运行
        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            log_info "容器正在运行中"
            return 0
        else
            log_info "启动已停止的容器..."
            docker start "$CONTAINER_NAME"
            return $?
        fi
    fi

    # 检查镜像是否存在
    if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${FULL_IMAGE}$"; then
        log_warn "镜像不存在，开始构建..."
        build_image
    fi

    log_info "启动新容器: $CONTAINER_NAME"

    # 构建 GPU 参数
    GPU_ARGS=""
    if [ "$GPU_DEVICE" = "all" ]; then
        GPU_ARGS="--gpus all"
    elif [ "$GPU_DEVICE" != "none" ]; then
        GPU_ARGS="--gpus device=$GPU_DEVICE"
    fi

    # 运行容器
    docker run -d \
        --name "$CONTAINER_NAME" \
        $GPU_ARGS \
        -p "${HOST_PORT}:${CONTAINER_PORT}" \
        \
        -e "APP_NAME=${APP_NAME}" \
        -e "APP_VERSION=${APP_VERSION}" \
        -e "LOG_LEVEL=${LOG_LEVEL}" \
        -e "HOST=${HOST}" \
        -e "PORT=${PORT}" \
        -e "WORKERS=${WORKERS}" \
        \
        -e "LVPOCKET_SOURCE_PATH=${LVPOCKET_SOURCE_PATH}" \
        \
        -e "MODEL_DIR=${MODEL_DIR}" \
        -e "MODEL_PATH=${MODEL_PATH}" \
        -e "MODEL_VERSION=${MODEL_VERSION}" \
        -e "SCALE=${SCALE}" \
        -e "MAX_DIST=${MAX_DIST}" \
        \
        -e "DEFAULT_STRUCTURE_CLASS=${DEFAULT_STRUCTURE_CLASS}" \
        \
        -e "DEFAULT_THRESHOLD=${DEFAULT_THRESHOLD}" \
        -e "DEFAULT_MIN_SIZE=${DEFAULT_MIN_SIZE}" \
        \
        -e "MAX_FILE_SIZE=${MAX_FILE_SIZE}" \
        -e "REQUEST_TIMEOUT=${REQUEST_TIMEOUT}" \
        \
        -e "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}" \
        -e "TF_FORCE_GPU_ALLOW_GROWTH=${TF_FORCE_GPU_ALLOW_GROWTH}" \
        -e "TF_CPP_MIN_LOG_LEVEL=${TF_CPP_MIN_LOG_LEVEL}" \
        \
        -v "${MODEL_DIR}:/app/model:ro" \
        -v "${INPUT_DIR}:/app/data/input" \
        -v "${OUTPUT_DIR}:/app/data/output" \
        \
        --restart unless-stopped \
        \
        "$FULL_IMAGE"

    if [ $? -eq 0 ]; then
        log_info "容器启动成功"
        log_info "API 地址: http://localhost:${HOST_PORT}"
        log_info "健康检查: http://localhost:${HOST_PORT}/api/v1/health"
        log_info "API 文档: http://localhost:${HOST_PORT}/docs"
    else
        log_error "容器启动失败"
        exit 1
    fi
}

# 停止容器
stop_container() {
    log_title "停止容器"
    check_docker

    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "停止容器: $CONTAINER_NAME"
        docker stop "$CONTAINER_NAME"
        log_info "容器已停止"
    else
        log_warn "容器未运行: $CONTAINER_NAME"
    fi
}

# 重启容器
restart_container() {
    log_title "重启容器"
    stop_container
    sleep 2
    start_container
}

# 查看日志
view_logs() {
    log_title "查看容器日志"
    check_docker

    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        docker logs -f "$CONTAINER_NAME"
    else
        log_error "容器不存在: $CONTAINER_NAME"
        exit 1
    fi
}

# 进入容器
exec_container() {
    log_title "进入容器"
    check_docker

    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "进入容器: $CONTAINER_NAME"
        docker exec -it "$CONTAINER_NAME" bash
    else
        log_error "容器未运行: $CONTAINER_NAME"
        exit 1
    fi
}

# 查看状态
show_status() {
    log_title "容器状态"
    check_docker

    echo ""
    echo "镜像信息:"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" | grep -E "(REPOSITORY|${IMAGE_NAME})" || echo "  镜像不存在"

    echo ""
    echo "容器信息:"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(NAMES|${CONTAINER_NAME})" || echo "  容器不存在"

    echo ""
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "服务运行中"
        echo ""
        echo "访问地址:"
        echo "  - API: http://localhost:${HOST_PORT}"
        echo "  - 健康检查: http://localhost:${HOST_PORT}/api/v1/health"
        echo "  - API 文档: http://localhost:${HOST_PORT}/docs"
    else
        log_warn "服务未运行"
    fi
}

# 清理
clean() {
    log_title "清理容器和镜像"
    check_docker

    # 停止并删除容器
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "停止并删除容器: $CONTAINER_NAME"
        docker stop "$CONTAINER_NAME" 2>/dev/null
        docker rm "$CONTAINER_NAME"
    fi

    # 询问是否删除镜像
    read -p "是否删除镜像 $FULL_IMAGE? [y/N]: " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${FULL_IMAGE}$"; then
            log_info "删除镜像: $FULL_IMAGE"
            docker rmi "$FULL_IMAGE"
        fi
    fi

    log_info "清理完成"
}

# 显示帮助
show_help() {
    echo "LVPocket Service Docker 启动脚本"
    echo ""
    echo "使用方法: $0 <命令>"
    echo ""
    echo "命令:"
    echo "  build    构建 Docker 镜像"
    echo "  start    启动容器"
    echo "  stop     停止容器"
    echo "  restart  重启容器"
    echo "  logs     查看容器日志（实时）"
    echo "  exec     进入容器 shell"
    echo "  status   查看容器状态"
    echo "  clean    清理容器和镜像"
    echo "  help     显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 build      # 构建镜像"
    echo "  $0 start      # 启动服务"
    echo "  $0 logs       # 查看日志"
    echo ""
    echo "配置修改:"
    echo "  编辑脚本顶部的配置区域可修改:"
    echo "  - 端口映射 (HOST_PORT)"
    echo "  - GPU 设备 (GPU_DEVICE)"
    echo "  - 预测参数 (DEFAULT_THRESHOLD, DEFAULT_MIN_SIZE)"
    echo "  - 其他环境变量"
}

# ==================== 主入口 ====================

case "${1:-help}" in
    build)
        build_image
        ;;
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        restart_container
        ;;
    logs)
        view_logs
        ;;
    exec)
        exec_container
        ;;
    status)
        show_status
        ;;
    clean)
        clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "未知命令: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
