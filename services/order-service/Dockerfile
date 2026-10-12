# ---- Stage 1: build a virtualenv with production dependencies only ----
FROM python:3.12-slim AS deps
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: small runtime image, no build tools, runs as an unprivileged user ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    SERVICE_NAME=order-service \
    PORT=3001 \
    DB_PATH=/data/service.db
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY app ./app


# writable data directory owned by the unprivileged user
RUN useradd --system --uid 10001 appuser && mkdir -p /data && chown -R appuser /data /app
USER appuser
EXPOSE 3001
VOLUME ["/data"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD python -c "import os,urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/health', timeout=2)" || exit 1
CMD ["python", "-m", "app.main"]
