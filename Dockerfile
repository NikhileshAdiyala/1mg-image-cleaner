FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for ONNX runtime and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the U2-Net AI model during build for instant container startup
RUN python -c "from rembg import new_session; new_session('u2net')"

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
