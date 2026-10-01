"""留言板业务服务（backend）

职责：留言的增删查、访问计数、实例命中统计。
存储：Redis（生产路径）；当 STORAGE_MODE=memory 时退化为进程内存，
      仅用于“物理机直接运行”这一消融基线，便于在没有 Redis 的宿主机上对比。
所有配置均来自环境变量，在 K8s 中由 ConfigMap / Secret 注入。
"""
import json
import os
import socket
import time
import uuid

from flask import Flask, jsonify, request

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
STORAGE_MODE = os.getenv("STORAGE_MODE", "redis")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "50"))
MAX_CONTENT_LEN = int(os.getenv("MAX_CONTENT_LEN", "200"))

# 实例标识：K8s 中通过 Downward API 注入 POD_NAME / NODE_NAME，
# Docker 中为容器 ID 前缀（即 hostname）。
INSTANCE = os.getenv("POD_NAME") or socket.gethostname()
NODE = os.getenv("NODE_NAME", "-")
STARTED_AT = time.time()

app = Flask(__name__)
app.json.ensure_ascii = False  # 中文错误信息直接输出，不转义为 Unicode 码点


class MemoryStore:
    """与 RedisStore 接口一致的内存实现。"""

    def __init__(self):
        self.messages, self.counters, self.hits = [], {}, {}

    def ping(self):
        return True

    def add_message(self, msg):
        self.messages.insert(0, msg)
        del self.messages[MAX_MESSAGES:]

    def list_messages(self, limit):
        return self.messages[:limit]

    def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def get(self, key):
        return self.counters.get(key, 0)

    def hit(self, instance):
        self.hits[instance] = self.hits.get(instance, 0) + 1

    def all_hits(self):
        return dict(self.hits)


class RedisStore:
    def __init__(self):
        import redis

        self.r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    def ping(self):
        return self.r.ping()

    def add_message(self, msg):
        pipe = self.r.pipeline()
        pipe.lpush("gb:messages", json.dumps(msg, ensure_ascii=False))
        pipe.ltrim("gb:messages", 0, MAX_MESSAGES - 1)
        pipe.execute()

    def list_messages(self, limit):
        return [json.loads(x) for x in self.r.lrange("gb:messages", 0, limit - 1)]

    def incr(self, key):
        return self.r.incr("gb:" + key)

    def get(self, key):
        return int(self.r.get("gb:" + key) or 0)

    def hit(self, instance):
        self.r.hincrby("gb:hits", instance, 1)

    def all_hits(self):
        return {k: int(v) for k, v in self.r.hgetall("gb:hits").items()}


store = MemoryStore() if STORAGE_MODE == "memory" else RedisStore()


def instance_info():
    return {
        "service": "backend",
        "instance": INSTANCE,
        "node": NODE,
        "version": APP_VERSION,
        "storage": STORAGE_MODE,
        "uptime_s": round(time.time() - STARTED_AT, 1),
    }


@app.get("/api/info")
def info():
    return jsonify(instance_info())


@app.post("/api/visit")
def visit():
    """记录一次访问，并返回由哪个实例处理——用于观察负载分发。"""
    total = store.incr("visits")
    store.hit(INSTANCE)
    return jsonify({"visits": total, "served_by": INSTANCE})


@app.get("/api/messages")
def list_messages():
    limit = min(int(request.args.get("limit", 20)), MAX_MESSAGES)
    return jsonify({"items": store.list_messages(limit), "served_by": INSTANCE})


@app.post("/api/messages")
def add_message():
    data = request.get_json(silent=True) or {}
    author = str(data.get("author", "")).strip()[:20] or "匿名"
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify({"error": "content 不能为空"}), 400
    if len(content) > MAX_CONTENT_LEN:
        return jsonify({"error": f"content 超过 {MAX_CONTENT_LEN} 字"}), 400
    msg = {
        "id": uuid.uuid4().hex[:8],
        "author": author,
        "content": content,
        "ts": int(time.time()),
        "written_by": INSTANCE,
    }
    store.add_message(msg)
    store.incr("messages_total")
    return jsonify(msg), 201


@app.get("/api/stats")
def stats():
    return jsonify(
        {
            "visits": store.get("visits"),
            "messages_total": store.get("messages_total"),
            "hits_by_instance": store.all_hits(),
            "served_by": INSTANCE,
        }
    )


@app.get("/healthz")
def healthz():
    """存活探针：只要进程能响应即视为存活。"""
    return jsonify({"status": "ok", "instance": INSTANCE})


@app.get("/readyz")
def readyz():
    """就绪探针：只反映本实例能否处理请求。

    v1.0 曾在这里检查 Redis，结果 Redis 重建期间所有副本同时被判为未就绪、
    被一起摘出 Service，连不依赖存储的接口也全部不可用（级联故障）。
    共享依赖的状态改由 /api/deps 暴露，存储故障只影响用到存储的接口（返回 503）。
    """
    return jsonify({"status": "ready", "instance": INSTANCE})


@app.get("/api/deps")
def deps():
    try:
        store.ping()
        return jsonify({"storage": "up", "instance": INSTANCE})
    except Exception as e:  # noqa: BLE001
        return jsonify({"storage": "down", "error": str(e), "instance": INSTANCE}), 503


if STORAGE_MODE != "memory":
    import redis as _redis

    @app.errorhandler(_redis.exceptions.RedisError)
    def storage_unavailable(e):
        """存储不可用时快速失败为 503，而不是让请求挂起或返回 500。"""
        return jsonify({"error": "storage unavailable", "detail": str(e), "served_by": INSTANCE}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
