# KerrOS event-mesh node image (C-17 / ADR-011).
# Build context: repository root.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KERROS_BASE=/app \
    KERROS_EVENT_MESH=1 \
    KERROS_EVENT_MESH_TRANSPORT=http \
    KERROS_EVENT_MESH_LISTEN=0.0.0.0:8787

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8787

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=2)"

CMD ["python3", "scripts/mesh_node.py"]
