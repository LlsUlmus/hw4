#!/usr/bin/env bash
# 隔离性对比：同一台虚拟机内，分别从“虚拟机本身 / Docker 容器 / K8s Pod”三个视角
# 观察进程、主机名、网络接口、根文件系统、内核版本与内存限制。
IMG=${IMG:-hw4/backend:1.1}
PY='import os,socket,platform
procs=[p for p in os.listdir("/proc") if p.isdigit()]
ifs=[l.split(":")[0].strip() for l in open("/proc/net/dev").readlines()[2:]]
pid1=" ".join(open("/proc/1/cmdline").read().replace("\0"," ").split())[:45]
root=sorted(os.listdir("/"))[:8]
lim="-"
for f in ("/sys/fs/cgroup/memory/memory.limit_in_bytes","/sys/fs/cgroup/memory.max"):
    if os.path.exists(f):
        v=open(f).read().strip(); lim="unlimited" if (not v.isdigit() or int(v)>2**60) else "%d MiB"%(int(v)//2**20); break
print("  hostname   :", socket.gethostname())
print("  processes  :", len(procs), "| PID 1 =", pid1)
print("  interfaces :", ",".join(ifs))
print("  kernel     :", platform.release())
print("  mem limit  :", lim)
print("  / entries  :", " ".join(root))'

echo "[1] VirtualBox VM (Ubuntu 20.04)"
python3 -c "$PY"
echo "[2] Docker container (docker run --rm $IMG)"
docker run --rm -m 256m -e STORAGE_MODE=memory "$IMG" python -c "$PY"
echo "[3] K8s Pod (kubectl exec deploy/backend)"
kubectl -n hw4 exec deploy/backend -- python -c "$PY"
echo "[4] namespaces of the Docker container's PID 1, seen from the VM"
CID=$(docker run -d --rm -e STORAGE_MODE=memory "$IMG")
PID=$(docker inspect -f '{{.State.Pid}}' "$CID")
sudo lsns -p "$PID" -o NS,TYPE,NPROCS,PID,COMMAND | sed 's/^/  /'
docker rm -f "$CID" >/dev/null
