FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-dev \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy workflow code
COPY workflows/ ./workflows/
COPY jenkins/ ./jenkins/

# Make workflow executable
RUN chmod +x workflows/workflow1.py

# Default command
CMD ["python", "workflows/workflow1.py"]