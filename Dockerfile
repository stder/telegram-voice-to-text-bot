FROM python:3.14-slim

# libgomp1 — the OpenMP runtime; CTranslate2 (the faster-whisper engine) won't start
# without it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run unprivileged. /models is created here so that the named volume mounted over it
# inherits this ownership and the model download can write to it.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /models \
    && chown -R app:app /models /app
USER app

ENV HF_HOME=/models \
    PYTHONUNBUFFERED=1

# The polling loop touches /tmp/heartbeat every 30s. A stale timestamp means the event
# loop is wedged even though the process is still alive. The long start period covers
# the first run, which downloads the model weights before polling begins.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15m --retries=3 \
    CMD ["python", "-c", "import os,sys,time; p='/tmp/heartbeat'; sys.exit(0 if os.path.exists(p) and time.time() - os.path.getmtime(p) < 120 else 1)"]

CMD ["python", "-m", "app"]
