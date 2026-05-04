# Agentic: Horizontally-Scalable Claude Agent System

> **Production-ready distributed agent system**: Claude-powered agents that think, decide, and act—running on your infrastructure with horizontal scalability.

A **high-performance, fault-tolerant agent system** using API + Worker + Redis pattern with **progressive skill disclosure** and **browser automation**.

## 🎯 What This Does

- **API + Worker + Redis Pattern**: Lightweight API submits tasks, stateless workers execute them, Redis stores state
- **Horizontally Scalable**: Scale workers with `docker-compose up --scale worker=N`
- **Claude as Intelligence**: Uses Anthropic's Claude API for decision-making
- **5 Built-in Tools**: Data extraction, database queries, API calls, file reading, web scraping
- **Browser Automation**: Headless Chromium via Playwright for web scraping
- **Fault Tolerance**: Redis checkpointing every N steps for recovery
- **Progressive Skills**: Load skill metadata only by default, full content on-demand
- **Fast API**: Stateless API returns immediately, non-blocking task execution

## 🏗️ System Architecture

![Architecture Diagram](ARCHITECTURE_DIAGRAM.svg)

**System Components:**
- `api.py` - Lightweight REST API (port 8000)
- `worker.py` - Task execution agents
- `agent_instance.py` - Claude agent core
- `tools/custom_tools.py` - Tool implementations
- `docker-compose.yml` - Service orchestration
- `Redis` - Queue + state storage

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose (v2.0+)
- Anthropic API key: https://console.anthropic.com

### 1. Create .env File

```bash
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=sk-...
```

### 2. Build & Start

```bash
# Build images
docker-compose build

# Start services (api, 2 workers, redis)
docker-compose up -d

# Verify health
curl http://localhost:8000/health
# Should return: {"status": "healthy", "redis_available": true, ...}
```

### 3. Submit a Task

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Extract emails from: john@example.com and jane@acme.io",
    "max_steps": 5
  }'

# Response:
# {"task_id": "550e8400-...", "status": "queued", "created_at": "2026-05-03T..."}
```

### 4. Poll Results

```bash
# From response above, get task_id and poll:
curl http://localhost:8000/tasks/{task_id}

# Response:
# {
#   "task_id": "550e8400-...",
#   "status": "completed",
#   "result": "Found emails: john@example.com, jane@acme.io",
#   "steps_taken": 2,
#   "duration_seconds": 3.45
# }
```

**That's it! You have a working agent system.** 🎉

## 📋 Task Execution Flow

### 1. Submit Task
```
User/AI → POST /tasks with {input, max_steps, timeout}
         ↓
         API generates task_id, stores in Redis, queues task
         ↓
         Returns immediately: {task_id, status: "queued"}
```

### 2. Worker Processes Task
```
Worker polls Redis queue (blocking blpop)
       ↓
       Dequeues task, marks status: "running"
       ↓
       Loads checkpoint (if exists)
       ↓
       Calls run_agent(task_data) with hard timeout
       ↓
       Every N steps, saves checkpoint to Redis
       ↓
       On completion, stores result, clears checkpoint
       ↓
       Updates status: "completed" or "failed" or "timeout"
```

### 3. Poll for Results
```
User/AI → GET /tasks/{task_id}
         ↓
         Returns current status, result (if done), steps_taken, duration
         ↓
         Client polls every 1-2 seconds until completion
```

## 🔄 API Reference

### Health Check

```bash
GET /health

Response:
{
  "status": "healthy",
  "redis_available": true,
  "timestamp": "2026-05-03T..."
}
```

### List Skills

```bash
GET /skills

Response:
{
  "count": 3,
  "skills": [
    {"name": "data-extraction", "description": "Extract emails, phones, URLs"},
    {"name": "web-research", "description": "Research topics and extract insights"},
    ...
  ]
}
```

### Submit Task

```bash
POST /tasks

Body:
{
  "input": "Your task description here",
  "max_steps": 10,      # Optional (1-100, default 10)
  "timeout": 300        # Optional (10-3600s, default 300)
}

Response:
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-05-03T12:00:00Z"
}
```

### Get Task Status

```bash
GET /tasks/{task_id}

Response:
{
  "task_id": "550e8400-...",
  "status": "queued|running|completed|failed|timeout",
  "input": "Extract emails from...",
  "result": "Found: john@example.com, jane@test.org",
  "error": null,
  "steps_taken": 2,
  "duration_seconds": 3.45,
  "created_at": "2026-05-03T12:00:00Z",
  "started_at": "2026-05-03T12:00:01Z",
  "completed_at": "2026-05-03T12:00:04Z"
}
```

### List Tasks

```bash
GET /tasks?status=completed&limit=50

Response:
{
  "count": 5,
  "limit": 50,
  "tasks": [
    {
      "task_id": "550e8400-...",
      "status": "completed",
      "created_at": "2026-05-03T12:00:00Z",
      "input_preview": "Extract emails from..."
    },
    ...
  ]
}
```

### Queue Depth

```bash
GET /queue/depth

Response:
{
  "queued": 2,
  "running": 1
}
```

### Configuration Info

```bash
GET /info

Response:
{
  "version": "2.0.0",
  "redis_url": "redis://localhost:6379/0",
  "task_ttl_seconds": 86400,
  "timestamp": "2026-05-03T..."
}
```

## 🛠️ Common Tasks

### Extract Data from Text

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Extract all phone numbers from: Call us at 555-123-4567 or 555-987-6543",
    "max_steps": 5
  }' | jq -r '.task_id'

# Then poll: curl http://localhost:8000/tasks/{task_id}
```

### Visit a Website

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Visit https://example.com and extract the main heading",
    "max_steps": 5,
    "timeout": 60
  }' | jq -r '.task_id'
```

### Query Sample Database

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Query the database: SELECT * FROM sample LIMIT 5",
    "max_steps": 5
  }' | jq -r '.task_id'
```

### Call External API

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Call https://jsonplaceholder.typicode.com/users and get the first user",
    "max_steps": 5
  }' | jq -r '.task_id'
```

## 📊 Scaling Workers

The system starts with **2 workers**. Scale up for more throughput:

```bash
# Scale to 5 workers
docker-compose up -d --scale worker=5

# Verify
docker-compose ps | grep worker

# Scale back down
docker-compose up -d --scale worker=2
```

**Performance Notes**:
- Each worker can handle ~1-3 tasks/minute (depending on task complexity)
- 2 workers: ~2-6 tasks/minute throughput
- 5 workers: ~5-15 tasks/minute throughput
- Queue depth is visible via: `curl http://localhost:8000/queue/depth`

## 🔍 Monitoring

### Check Queue Depth

```bash
curl http://localhost:8000/queue/depth | jq .

# Response: {"queued": 2, "running": 1}
```

### View Worker Logs

```bash
# All workers
docker-compose logs worker

# Specific worker
docker logs agentic-worker-1

# Follow in real-time
docker-compose logs -f worker
```

### Check Configuration

```bash
curl http://localhost:8000/info | jq .
```

### List All Tasks

```bash
curl http://localhost:8000/tasks | jq .
```

## 🔐 Tool Access

Workers have access to 5 built-in tools:

| Tool | Purpose | Example |
|------|---------|---------|
| `extract_structured_data` | Extract emails, phones, URLs | `"Extract emails from: john@example.com"` |
| `query_database` | SQL SELECT queries | `"SELECT * FROM sample LIMIT 10"` |
| `call_external_api` | Call REST APIs (whitelisted) | `"Get https://jsonplaceholder.typicode.com/users"` |
| `read_file` | Read files from safe dirs | Automatically used to load skills |
| `browse_web` | Web scraping + automation | `"Visit https://example.com and extract..."` |

## 💡 Client Usage Example

```python
import requests
import time

BASE_URL = "http://localhost:8000"

# 1. Submit task
response = requests.post(f"{BASE_URL}/tasks", json={
    "input": "Extract emails from: john@example.com, jane@test.org",
    "max_steps": 5
})
task_id = response.json()["task_id"]
print(f"Task submitted: {task_id}")

# 2. Poll until completion
max_wait = 60
for i in range(max_wait):
    status = requests.get(f"{BASE_URL}/tasks/{task_id}").json()
    
    if status["status"] == "completed":
        print(f"✅ Completed in {status['duration_seconds']}s")
        print(f"Result: {status['result']}")
        break
    elif status["status"] == "failed":
        print(f"❌ Failed: {status['error']}")
        break
    else:
        print(f"  Status: {status['status']} ({i}s)")
        time.sleep(1)
```

## 🔄 Complete Workflow Script

```bash
#!/bin/bash

# 1. Submit task
TASK_ID=$(curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Visit deeplearning.ai and find 3 free short courses",
    "max_steps": 10,
    "timeout": 60
  }' | jq -r '.task_id')

echo "Task submitted: $TASK_ID"

# 2. Poll for completion
while true; do
  STATUS=$(curl -s http://localhost:8000/tasks/$TASK_ID | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "completed" ]; then
    echo "✅ Task completed!"
    curl -s http://localhost:8000/tasks/$TASK_ID | jq '.result'
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "❌ Task failed"
    curl -s http://localhost:8000/tasks/$TASK_ID | jq '.error'
    break
  fi
  
  sleep 2
done
```

## 🔧 Configuration

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-...                    # Your API key

# Optional
CLAUDE_MODEL=claude-sonnet-4-6              # Model selection
REDIS_URL=redis://localhost:6379/0          # Redis connection
TASK_TTL_SECONDS=86400                      # Task retention (24h)
CHECKPOINT_INTERVAL=3                       # Save checkpoint every N steps
SKILLS_DIR=/app/.claude/skills              # Path to skills
```

### Docker Compose Configuration

Edit `docker-compose.yml` to adjust:
- **Worker replicas**: `deploy.replicas`
- **Resource limits**: `mem_limit`, `cpus`
- **Redis persistence**: Already enabled
- **Health checks**: Configured for all services

## 🚨 Troubleshooting

| Problem | Solution |
|---------|----------|
| `ANTHROPIC_API_KEY not set` | Add to .env: `ANTHROPIC_API_KEY=sk-...` |
| `Connection refused on :8000` | Wait for startup: `sleep 10` |
| `Connection refused on :6379` | Check Redis: `docker-compose logs redis` |
| Task stuck in `running` | Check worker: `docker logs agentic-worker-1` |
| Task timeout | Increase: `"timeout": 600` |
| Worker crashed | Check logs: `docker-compose logs worker` |
| No results after completion | Verify status: `curl http://localhost:8000/tasks/{id}` |
| Slow task processing | Check queue depth: `curl http://localhost:8000/queue/depth`, scale workers up |

## 📖 Documentation

- **[GETTING_STARTED.md](GETTING_STARTED.md)** - 5-minute setup guide
- **[SETUP_AUTONOMOUS.md](SETUP_AUTONOMOUS.md)** - Autonomous AI deployment guide
- **[CLAUDE.md](CLAUDE.md)** - Architecture & design decisions

## ✅ What You Have

- ✅ Fast REST API on port 8000
- ✅ Worker pool (default 2, horizontally scalable)
- ✅ Redis queue & persistent state store
- ✅ 5 built-in tools
- ✅ Browser automation with Chromium
- ✅ Fault tolerance & checkpointing
- ✅ Task logging & monitoring
- ✅ Progressive skill disclosure

**You're ready to process tasks!** 🚀

## 🎯 Next Steps

1. **Setup**: Run quick start above
2. **Test**: Submit a task and poll results
3. **Learn**: Read [CLAUDE.md](CLAUDE.md) for architecture details
4. **Monitor**: Check queue depth and worker logs
5. **Scale**: `docker-compose up --scale worker=5`
6. **Deploy**: Follow [SETUP_AUTONOMOUS.md](SETUP_AUTONOMOUS.md) for production

---

**Built with ❤️ using Claude, Docker, and Redis**

Questions? Check [GETTING_STARTED.md](GETTING_STARTED.md) or [SETUP_AUTONOMOUS.md](SETUP_AUTONOMOUS.md).
