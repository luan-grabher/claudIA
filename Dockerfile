FROM python:3.11-slim

# Install system tools needed by the shell skill (common Linux utilities)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    build-essential \
    net-tools \
    iputils-ping \
    procps \
    htop \
    vim \
    nano \
    unzip \
    zip \
    jq \
    sudo \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data directory for persistent state (first-run marker, etc.)
RUN mkdir -p /app/data

VOLUME ["/app/data"]

CMD ["python", "main.py"]
