#!/usr/bin/env bash
# 持续访问探测：每 0.2 秒请求一次 /api/whoami，打印时间、HTTP 状态码与处理实例。
# 用于验证 Pod 删除 / 滚动更新期间服务是否中断。结束后输出成功率统计。
#   ./probe.sh http://127.0.0.1:30080 60
URL=${1:-http://127.0.0.1:30080}
DURATION=${2:-60}
ok=0; fail=0
end=$((SECONDS + DURATION))
trap 'echo; echo "== total $((ok+fail))  ok $ok  fail $fail"; exit' INT
while [ $SECONDS -lt $end ]; do
  out=$(curl -s -m 2 -w ' %{http_code}' "$URL/api/whoami")
  code=${out##* }
  be=$(echo "$out" | sed -n 's/.*"backend":"\([^"]*\)".*/\1/p')
  gw=$(echo "$out" | sed -n 's/.*"gateway":"\([^"]*\)".*/\1/p')
  if [ "$code" = "200" ]; then ok=$((ok+1)); else fail=$((fail+1)); fi
  printf '%s  %s  gw=%-28s be=%s\n' "$(date +%H:%M:%S.%3N)" "$code" "$gw" "$be"
  sleep 0.2
done
echo "== total $((ok+fail))  ok $ok  fail $fail"
