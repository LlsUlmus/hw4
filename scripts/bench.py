#!/usr/bin/env python3
"""轻量压测脚本（仅依赖标准库，兼容 Python 3.8+）。

用法：
  python3 bench.py http://127.0.0.1:8080/api/whoami -n 2000 -c 20

输出：总请求数、失败数、吞吐量 (req/s)、平均/P50/P95/P99 延迟，以及各后端实例命中分布。
"""
import argparse
import json
import statistics
import threading
import time
import urllib.request
from collections import Counter


def worker(url, count, lat, fails, dist, lock):
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read()
            dt = (time.perf_counter() - t0) * 1000
            inst = None
            try:
                d = json.loads(body)
                inst = d.get("backend") or d.get("instance") or d.get("served_by")
            except ValueError:
                pass
            with lock:
                lat.append(dt)
                if inst:
                    dist[inst] += 1
        except Exception:  # noqa: BLE001
            with lock:
                fails.append(1)


def pct(data, p):
    data = sorted(data)
    k = max(0, min(len(data) - 1, int(round(p / 100.0 * len(data))) - 1))
    return data[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("-n", type=int, default=1000, help="总请求数")
    ap.add_argument("-c", type=int, default=10, help="并发数")
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    lat, fails, dist, lock = [], [], Counter(), threading.Lock()
    per = a.n // a.c
    threads = [threading.Thread(target=worker, args=(a.url, per, lat, fails, dist, lock)) for _ in range(a.c)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    total = per * a.c
    print("label      :", a.label or a.url)
    print("requests   : %d  (concurrency %d)" % (total, a.c))
    print("failed     : %d" % len(fails))
    print("elapsed    : %.2f s" % elapsed)
    print("throughput : %.1f req/s" % (len(lat) / elapsed))
    if lat:
        print("latency ms : avg %.2f | p50 %.2f | p95 %.2f | p99 %.2f | max %.2f" % (
            statistics.mean(lat), pct(lat, 50), pct(lat, 95), pct(lat, 99), max(lat)))
    if dist:
        print("instances  :")
        for k, v in sorted(dist.items()):
            print("   %-40s %d" % (k, v))


if __name__ == "__main__":
    main()
