# LangGraph Agent Container
# Runs a single isolated Plan-and-Execute LangGraph agent instance.

FROM python:3.12-slim

WORKDIR /app

# System dependencies (includes Chromium for optional browser tools)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    chromium \
    libnss3 \
    libxss1 \
    libnspr4 \
    libxslt1.1 \
    fonts-liberation \
    xdg-utils \
    libgbm1 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY langgraph_agent.py .
COPY tools/ ./tools/
COPY .claude/ ./.claude/

# Runtime directories
RUN mkdir -p /workspace /memory /data

ENV BROWSERLESS_HEADLESS=true
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import langgraph, langchain_anthropic; import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["python"]
CMD ["langgraph_agent.py"]
