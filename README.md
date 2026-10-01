# 云原生留言板：从虚拟化到容器编排的消融对比实验

《云计算技术》作业四。同一个三组件应用（gateway + backend + Redis）依次以
**物理机进程 → 虚拟机进程 → Docker / Compose → kind 多节点 K8s → 嵌套虚拟机中的 minikube**
五种方式部署，对比启动时间、资源占用、性能、隔离性与运维能力。

## 目录结构

```
src/         应用源码（gateway：页面与 API 转发；backend：留言/计数/实例统计）
docker/      Dockerfile、docker-compose.yml、.env
k8s/         K8s 资源清单（按序号 apply）；cluster/ 下为集群与插件清单
scripts/     压测、持续探测、启动计时、隔离性检查、Redis 重建测试脚本
data/        实验原始数据（压测输出、启动时间、virsh 统计）
screenshots/ 实验截图，按验证项分目录
report/      报告插图
.github/     CI 流水线（语法检查 → 构建镜像 → compose 冒烟测试 → 清单校验 → 推送 GHCR）
```

## 实验环境

| 项 | 版本 |
|---|---|
| 宿主机 | Windows 11 家庭中文版，i9-13900HX，16 GB |
| 虚拟机 | VirtualBox 7.1.4，Ubuntu 20.04.6，4 vCPU / 6 GB，开启嵌套 VT-x |
| 容器 | Docker 28.1.1，Compose v2.35.1 |
| 编排 | kind v0.24.0（K8s v1.31.0，1 控制面 + 2 工作节点）；minikube v1.34.0（kvm2 驱动，嵌套） |
| 应用 | Python 3.11，Flask 3.0，gunicorn 22，Redis 7 |

## 复现步骤

以下命令均在仓库根目录执行（Linux / 虚拟机内）。

### 1. 构建镜像

```bash
docker build -f docker/backend.Dockerfile -t hw4/backend:1.1 .
docker build -f docker/gateway.Dockerfile -t hw4/gateway:1.0 .
```

国内网络默认使用阿里云 PyPI 镜像，可用 `--build-arg PIP_INDEX_URL=...` 覆盖。

### 2. Docker Compose 路径

```bash
export COMPOSE_FILE=docker/docker-compose.yml COMPOSE_ENV_FILES=docker/.env
docker compose up -d --build
docker compose up -d --scale backend=3 --no-recreate
curl localhost:8080/api/whoami          # 返回处理请求的 gateway / backend 实例
```

### 3. Kubernetes 路径（kind）

```bash
kind create cluster --config k8s/cluster/kind-cluster.yaml
kind load docker-image hw4/backend:1.1 hw4/gateway:1.0 redis:7-alpine --name hw4
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/                    # ConfigMap/Secret/Redis/backend/gateway/Ingress/PDB/HPA
kubectl apply -f k8s/cluster/metrics-server.yaml          # HPA 与 kubectl top 依赖
kubectl apply -f k8s/cluster/ingress-nginx-kind.yaml      # Ingress 控制器
curl localhost:30080/api/whoami          # NodePort
echo "127.0.0.1 hw4.local" | sudo tee -a /etc/hosts && curl hw4.local/api/whoami   # Ingress
```

### 4. 验证脚本

```bash
scripts/probe.sh http://localhost:30080 60        # 持续访问，统计失败数（配合删 Pod / 缩容 / 排空节点）
python3 scripts/bench.py http://localhost:30080/api/whoami -n 2000 -c 20
scripts/startup_time.sh native|docker|k8s         # 启动到 /healthz 可用的耗时
scripts/redis_restart_test.sh                     # Redis Pod 重建期间存储接口不可用窗口
scripts/isolation_check.sh                        # 虚拟机 / 容器 / Pod 的隔离视图对比
scripts/run_native.sh start|stop                  # 不用容器，直接以进程运行（消融基线）
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 留言板页面 |
| GET | `/api/whoami` | 返回本次请求经过的 gateway 与 backend 实例、节点 |
| GET/POST | `/api/messages` | 留言列表 / 发表留言 |
| POST | `/api/visit`、GET `/api/stats` | 访问计数与各实例命中统计 |
| GET | `/healthz`、`/readyz`、`/api/deps` | 存活、就绪、依赖状态 |

## 实验中修正的问题（详见报告第六章）

- 就绪探针检查 Redis 导致级联摘流 → `/readyz` 只反映自身，依赖状态改由 `/api/deps` 暴露（backend v1.1）
- 业务直连 `redis-0.redis` 时，Redis 重建后受 DNS 缓存影响约 19 s 不可用 → 新增 ClusterIP Service `redis-master`
- 缩容时出现 502 → 增加 `preStop: sleep 5`
- PDB `minAvailable: 2` 与 HPA 最小副本数 2 冲突，节点排空被永久阻塞 → 改为 `maxUnavailable: 1`
- 未设 CPU limit 与设置 500m limit 时吞吐相差一倍（CFS 节流）
