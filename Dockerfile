FROM python:3.11-slim

WORKDIR /app

# System deps KerrOS likely needs (adjust as needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist RAG store / memory outside the image
VOLUME ["/app/knowledge", "/app/memory", "/app/data"]

EXPOSE 8000

CMD ["python", "cli/chat.py"]
