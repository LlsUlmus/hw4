"""网关服务（gateway）

职责：
  1. 提供前端静态页面；
  2. 把 /api/* 请求转发给 backend（服务发现地址由 BACKEND_URL 配置）；
  3. 在每个响应中附加网关自身实例标识，使“请求经过了哪个网关、哪个后端”一目了然。
"""
import os
import socket
import time

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000").rstrip("/")
APP_TITLE = os.getenv("APP_TITLE", "云原生留言板")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "3"))
INSTANCE = os.getenv("POD_NAME") or socket.gethostname()
STARTED_AT = time.time()

app = Flask(__name__, static_folder="static")
session = requests.Session()


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/config.json")
def config():
    return jsonify({"title": APP_TITLE, "version": APP_VERSION})


@app.get("/api/whoami")
def whoami():
    """一次请求同时返回网关实例与后端实例，便于验证负载分发。"""
    try:
        backend = session.get(f"{BACKEND_URL}/api/info", timeout=TIMEOUT).json()
    except requests.RequestException as e:
        return jsonify({"gateway": INSTANCE, "error": str(e)}), 502
    return jsonify(
        {
            "gateway": INSTANCE,
            "backend": backend.get("instance"),
            "backend_node": backend.get("node"),
            "version": APP_VERSION,
        }
    )


@app.route("/api/<path:path>", methods=["GET", "POST"])
def proxy(path):
    try:
        resp = session.request(
            request.method,
            f"{BACKEND_URL}/api/{path}",
            params=request.args,
            data=request.get_data(),
            headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        return jsonify({"gateway": INSTANCE, "error": f"backend unavailable: {e}"}), 502
    out = Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type"))
    out.headers["X-Gateway-Instance"] = INSTANCE
    return out


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "instance": INSTANCE, "uptime_s": round(time.time() - STARTED_AT, 1)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
