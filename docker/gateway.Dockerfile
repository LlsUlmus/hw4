# 网关镜像（构建上下文为仓库根目录）
#   docker build -f docker/gateway.Dockerfile -t hw4/gateway:1.0 .
FROM python:3.11-slim

# 国内网络默认使用阿里云 PyPI 镜像，CI 中可用 --build-arg 覆盖
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

COPY src/gateway/requirements.txt .
RUN pip install -r requirements.txt

COPY src/gateway/app.py .
COPY src/gateway/static ./static

RUN useradd --uid 10001 --no-create-home appuser
USER 10001

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)" || exit 1

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "--access-logfile", "-", "app:app"]
