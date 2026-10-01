# 业务服务镜像（构建上下文为仓库根目录）
#   docker build -f docker/backend.Dockerfile -t hw4/backend:1.0 .
FROM python:3.11-slim

# 国内网络默认使用阿里云 PyPI 镜像，CI 中可用 --build-arg 覆盖
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

# 先单独复制依赖清单，使依赖层可以被缓存，修改代码时不必重装依赖
COPY src/backend/requirements.txt .
RUN pip install -r requirements.txt

COPY src/backend/app.py .

# 以非 root 用户运行，降低容器逃逸后的影响面
RUN useradd --uid 10001 --no-create-home appuser
USER 10001

ENV PORT=5000
EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=2)" || exit 1

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--access-logfile", "-", "app:app"]
