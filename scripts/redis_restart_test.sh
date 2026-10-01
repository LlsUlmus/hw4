#!/usr/bin/env bash
# 观察 redis-0 被删除重建期间，存储类接口（/api/stats）的不可用时间窗口。
#   ./redis_restart_test.sh [URL] [观察秒数]
URL=${1:-http://localhost:30080}
DURATION=${2:-60}
out=/tmp/redis-restart.log; : > $out
(
  end=$((SECONDS + DURATION))
  while [ $SECONDS -lt $end ]; do
    printf "%s %s\n" "$(date +%T.%1N)" "$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$URL/api/stats")" >> $out
    sleep 0.2
  done
) &
sleep 3
echo "delete redis-0 at $(date +%T.%1N)"
kubectl -n hw4 delete pod redis-0 >/dev/null
kubectl -n hw4 wait --for=condition=Ready pod/redis-0 --timeout=90s >/dev/null
echo "redis-0 Ready at  $(date +%T.%1N)"
wait
echo "--- /api/stats status codes (count, code) ---"
awk '{print $2}' $out | uniq -c
echo "first 503: $(grep -m1 ' 503' $out | cut -d' ' -f1)   last 503: $(grep ' 503' $out | tail -1 | cut -d' ' -f1)"
