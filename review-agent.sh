#!/usr/bin/env bash
# review-agent 管理脚本
set -euo pipefail

APP_NAME="review-agent"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/$APP_NAME.log"
WORKER_LOG_FILE="$LOG_DIR/$APP_NAME-worker.log"
PID_FILE="$LOG_DIR/$APP_NAME.pid"
WORKER_PID_FILE="$LOG_DIR/$APP_NAME-worker.pid"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

mkdir -p "$LOG_DIR"

# ── 颜色输出 ──────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()    { echo -e "${GREEN}✔${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✘${NC} $*" >&2; }

# ── 帮助 ───────────────────────────────────────────────
usage() {
    cat <<EOF
${APP_NAME} — 管理脚本

用法:
    ./${0##*/} start      启动后台服务
    ./${0##*/} stop       停止后台服务
    ./${0##*/} restart    重启后台服务
    ./${0##*/} status     查看运行状态
    ./${0##*/} logs       实时查看日志 (tail -f)
    ./${0##*/} ps               查看进程
    ./${0##*/} worker {cmd}     Worker 管理 (start|stop|restart|logs)

环境变量:
    HOST      监听地址 (默认: 0.0.0.0)
    PORT      监听端口 (默认: 8000)
EOF
    exit 0
}

# ── 检测是否在运行 ─────────────────────────────────────
pid_of() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(<"$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    # fallback: 按进程名查找
    local pid
    pid=$(pgrep -f "uvicorn.*review_agent\.api" 2>/dev/null | tail -1 || true)
    if [[ -n "$pid" ]]; then
        echo "$pid"
        return 0
    fi
    return 1
}

# ── 启动 ───────────────────────────────────────────────
do_start() {
    if pid=$(pid_of); then
        warn "服务已在运行中 (PID: $pid)"
        return 0
    fi

    info "启动 $APP_NAME (HOST=$HOST PORT=$PORT)..."

    cd "$APP_DIR"

    nohup uv run uvicorn review_agent.api.app:app \
        --host "$HOST" \
        --port "$PORT" \
        >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    # 等待几秒确认启动
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        ok "服务已启动 (PID: $pid)"
        info "日志文件: $LOG_FILE"
        info "API 文档: http://$HOST:$PORT/docs"
        info "查看日志: ./${0##*/} logs"
    else
        err "服务启动失败，请检查日志:"
        tail -5 "$LOG_FILE" | sed 's/^/  /'
        rm -f "$PID_FILE"
        return 1
    fi
}

# ── 停止 ───────────────────────────────────────────────
do_stop() {
    if ! pid=$(pid_of); then
        warn "服务未在运行"
        return 0
    fi

    info "停止服务 (PID: $pid)..."
    kill "$pid" 2>/dev/null || true

    # 等待进程退出（最多 10 秒）
    local waited=0
    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
        waited=$((waited + 1))
        if [[ $waited -ge 10 ]]; then
            warn "强制终止 (PID: $pid)..."
            kill -9 "$pid" 2>/dev/null || true
            break
        fi
    done

    rm -f "$PID_FILE"
    ok "服务已停止"
}

# ── 状态 ───────────────────────────────────────────────
do_status() {
    if pid=$(pid_of); then
        local uptime
        if [[ "$(uname)" == "Darwin" ]]; then
            uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs || echo "?")
        else
            uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs || echo "?")
        fi
        echo -e "${GREEN}●${NC} 运行中  PID: ${CYAN}$pid${NC}  运行时间: ${YELLOW}$uptime${NC}"
        echo "  日志: $LOG_FILE"
    else
        echo -e "${RED}○${NC} 已停止"
        return 1
    fi
}

# ── 日志 ───────────────────────────────────────────────
do_logs() {
    if [[ ! -f "$LOG_FILE" ]]; then
        err "日志文件不存在: $LOG_FILE"
        return 1
    fi
    info "实时日志 (Ctrl+C 退出):"
    tail -f "$LOG_FILE"
}

# ── 进程 ───────────────────────────────────────────────
do_ps() {
    echo -e "${CYAN}服务进程:${NC}"
    ps aux | grep -E "uvicorn.*review_agent" | grep -v grep || echo "  (无)"
    echo
    echo -e "${CYAN}Worker 进程:${NC}"
    ps aux | grep -E "arq.*queue\.WorkerSettings" | grep -v grep || echo "  (无)"
    echo
    echo -e "${CYAN}数据服务 (docker):${NC}"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -E "(postgres|redis|review)" || echo "  (无)"
}

# ── Worker PID ──────────────────────────────────────────
worker_pid_of() {
    if [[ -f "$WORKER_PID_FILE" ]]; then
        local pid
        pid=$(<"$WORKER_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$WORKER_PID_FILE"
    fi
    local pid
    pid=$(pgrep -f "arq.*queue\.WorkerSettings" 2>/dev/null | tail -1 || true)
    if [[ -n "$pid" ]]; then
        echo "$pid"
        return 0
    fi
    return 1
}

# ── Worker 启动 ─────────────────────────────────────────
worker_start() {
    if pid=$(worker_pid_of); then
        warn "Worker 已在运行中 (PID: $pid)"
        return 0
    fi

    info "启动 ARQ Worker..."

    cd "$APP_DIR"
    nohup uv run arq src.review_agent.service.queue.WorkerSettings \
        >> "$WORKER_LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$WORKER_PID_FILE"

    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        ok "Worker 已启动 (PID: $pid)"
        info "Worker 日志: $WORKER_LOG_FILE"
        info "查看 Worker 日志: ./${0##*/} worker logs"
    else
        err "Worker 启动失败:"
        tail -5 "$WORKER_LOG_FILE" | sed 's/^/  /'
        rm -f "$WORKER_PID_FILE"
        return 1
    fi
}

# ── Worker 停止 ─────────────────────────────────────────
worker_stop() {
    if ! pid=$(worker_pid_of); then
        warn "Worker 未在运行"
        return 0
    fi

    info "停止 Worker (PID: $pid)..."
    kill "$pid" 2>/dev/null || true

    local waited=0
    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
        waited=$((waited + 1))
        if [[ $waited -ge 10 ]]; then
            warn "强制终止 Worker (PID: $pid)..."
            kill -9 "$pid" 2>/dev/null || true
            break
        fi
    done

    rm -f "$WORKER_PID_FILE"
    ok "Worker 已停止"
}

# ── Worker 日志 ─────────────────────────────────────────
worker_logs() {
    if [[ ! -f "$WORKER_LOG_FILE" ]]; then
        err "Worker 日志文件不存在: $WORKER_LOG_FILE"
        return 1
    fi
    info "Worker 实时日志 (Ctrl+C 退出):"
    tail -f "$WORKER_LOG_FILE"
}

# ── 主入口 ──────────────────────────────────────────────
case "${1:-help}" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_stop
        sleep 1
        do_start
        ;;
    status)
        do_status
        ;;
    logs)
        do_logs
        ;;
    ps)
        do_ps
        ;;
    worker)
        case "${2:-help}" in
            start)
                worker_start
                ;;
            stop)
                worker_stop
                ;;
            restart)
                worker_stop
                sleep 1
                worker_start
                ;;
            logs)
                worker_logs
                ;;
            *)
                echo "用法: ./${0##*/} worker {start|stop|restart|logs}"
                exit 1
                ;;
        esac
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        err "未知命令: $1"
        echo "用法: ./${0##*/} {start|stop|restart|status|logs|ps|help}"
        exit 1
        ;;
esac
