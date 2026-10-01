#!/usr/bin/env bash
# 启动时间测量：从发出启动指令到 /healthz 首次返回 200 的耗时（毫秒）。
#   ./startup_time.sh docker      # 单个 backend 容器（memory 模式）
#   ./startup_time.sh k8s         # 新建一个 backend Pod 直到 Ready
#   ./startup_time.sh native      # 虚拟机内直接运行 Python 进程
set -e
MODE=${1:-docker}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
now() { date +%s%3N; }

wait_http() {
  until curl -sf -m 1 "$1" >/dev/null; do sleep 0.05; done
}

case $MODE in
  native)
    t0=$(now)
    (cd "$ROOT/src/backend" && STORAGE_MODE=memory PORT=5900 python3 app.py >/dev/null 2>&1 &)
    wait_http http://127.0.0.1:5900/healthz
    t1=$(now)
    pkill -f "PORT=5900" || pkill -f "src/backend.*app.py" || true
    fuser -k 5900/tcp >/dev/null 2>&1 || true
    ;;
  docker)
    docker rm -f st-test >/dev/null 2>&1 || true
    t0=$(now)
    docker run -d --name st-test -e STORAGE_MODE=memory -p 5901:5000 hw4/backend:1.0 >/dev/null
    wait_http http://127.0.0.1:5901/healthz
    t1=$(now)
    docker rm -f st-test >/dev/null
    ;;
  k8s)
    kubectl -n hw4 delete pod st-test --ignore-not-found >/dev/null
    t0=$(now)
    kubectl -n hw4 run st-test --image=hw4/backend:1.0 --image-pull-policy=IfNotPresent \
      --env=STORAGE_MODE=memory --restart=Never >/dev/null
    kubectl -n hw4 wait --for=condition=Ready pod/st-test --timeout=120s >/dev/null
    t1=$(now)
    kubectl -n hw4 delete pod st-test --wait=false >/dev/null
    ;;
esac
echo "$MODE startup: $((t1 - t0)) ms"
