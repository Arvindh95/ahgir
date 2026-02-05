FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    g++ \
    libgl1 \
    libglib2.0-0 \
    patchelf \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fix onnxruntime executable stack issue
RUN find /usr/local/lib/python3.11/site-packages/onnxruntime -name "*.so" -exec patchelf --clear-execstack {} \; 2>/dev/null || true

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
