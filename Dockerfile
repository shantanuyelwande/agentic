# Claude Agent Container
# Runs a single isolated agent instance with browser automation support

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    # Browser automation dependencies (Playwright/Chromium)
    chromium-browser \
    chromium-codecs-ffmpeg \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libindicator7 \
    libnspr4 \
    libxslt1.1 \
    fonts-liberation \
    xdg-utils \
    libgbm1 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY agent_instance.py .
COPY tools/ ./tools/
COPY .claude/ ./.claude/
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (includes Chromium)
RUN playwright install chromium

# Create directories
RUN mkdir -p /workspace /memory /data

# Configure headless browser environment
ENV BROWSERLESS_HEADLESS=true
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Run agent
ENTRYPOINT ["python"]
CMD ["agent_instance.py"]
