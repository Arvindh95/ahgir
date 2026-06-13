# Person Re-Identification (Re-ID) sidecar.
#
# Wraps an OSNet-AIN ONNX model behind a small Flask app. The model file is
# NOT baked into the image; it is mounted at /app/models via a docker-compose
# volume. This keeps the image small (no ~MB-scale weights in CI / layer cache)
# and lets ops rotate the model without rebuilding.
#
# Build is intentionally pure-Python — onnxruntime ships portable wheels so
# no compilation or system libs beyond pillow's defaults are needed.

FROM python:3.11-slim

WORKDIR /app

# Match the rest of the stack: non-root user, predictable PYTHONUNBUFFERED so
# logs surface immediately under docker compose logs.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 reid

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY app.py /app/app.py
RUN mkdir -p /app/models && chown -R reid:reid /app

USER reid

EXPOSE 5000

# Gunicorn workers = 2 keeps two ONNX sessions warm. intra_op / inter_op are
# clamped inside app.py (we run on a CPU-only VPS and a single OSNet inference
# is small enough that thread fan-out hurts more than it helps).
CMD ["gunicorn", "-w", "2", "-t", "60", "-b", "0.0.0.0:5000", "app:app"]
