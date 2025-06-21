# Dockerfile for Swarm Multi-Agent System
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/src/database /tmp/swarm_workspace

# Set proper permissions
RUN chmod -R 755 /app && \
    chmod -R 777 /tmp/swarm_workspace

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash swarm && \
    chown -R swarm:swarm /app /tmp/swarm_workspace

# Switch to non-root user
USER swarm

# Expose port
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:10000/health || exit 1

# Start command
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "src.main:app"]

