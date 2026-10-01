#!/usr/bin/env bash
# 消融基线：不使用容器，直接以进程方式在当前主机运行 gateway + backend（memory 存储）。
#   ./run_native.sh start | stop
# 端口：gateway 8090，backend 5090；gunicorn 参数与容器镜像保持一致（-w 2）。
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VENV=${VENV:-$HOME/venv-hw4}
case ${1:-start} in
  start)
    cd "$ROOT/src/backend" && STORAGE_MODE=memory setsid "$VENV/bin/gunicorn" -w 2 -b 0.0.0.0:5090 app:app >/tmp/native-be.log 2>&1 &
    cd "$ROOT/src/gateway" && BACKEND_URL=http://127.0.0.1:5090 setsid "$VENV/bin/gunicorn" -w 2 -b 0.0.0.0:8090 app:app >/tmp/native-gw.log 2>&1 &
    until curl -sf -m 1 http://127.0.0.1:8090/healthz >/dev/null; do sleep 0.1; done
    echo "native gateway on :8090, backend on :5090"
    ;;
  stop)
    pkill -f "0.0.0.0:5090"; pkill -f "0.0.0.0:8090"; echo stopped
    ;;
esac
