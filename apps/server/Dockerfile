# Build from repository root: docker build -f apps/server/Dockerfile -t hqremote .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HQREMOTE_DATA_DIR=/data
WORKDIR /app
COPY packages/protocol /opt/protocol
COPY apps/server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt /opt/protocol \
    && groupadd --gid 10001 hqremote \
    && useradd --uid 10001 --gid 10001 --no-create-home hqremote \
    && mkdir /data && chown 10001:10001 /data && chmod 700 /data
COPY apps/server/server /app/server
USER 10001:10001
VOLUME ["/data"]
# Default remains loopback. Linux host networking allows a host Caddy to reach it.
# For bridge networks explicitly bind 0.0.0.0 and publish only 127.0.0.1:8080:8080.
EXPOSE 8080
CMD ["python", "-m", "server"]
