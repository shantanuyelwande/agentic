# Autonomous Setup Guide - AI-Driven Worker Spawning

> This document allows any AI system (Claude, GPT, etc.) to read instructions and autonomously set up and spawn agent workers without manual intervention.

## 📖 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites Check](#prerequisites-check)
3. [Configuration](#configuration)
4. [Deployment Steps](#deployment-steps)
5. [Verification](#verification)
6. [Scaling & Monitoring](#scaling--monitoring)

---

## Architecture Overview

The agentic system uses a **distributed API + Worker + Redis** pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                     TASK SUBMISSION (API)                    │
│         HTTP POST /tasks → Returns immediately              │
└────────────────────┬────────────────────────────────────────┘
                     │ (stores in Redis)
                     ▼
        ┌────────────────────────────┐
        │    REDIS TASK QUEUE        │
        │  - Persistent storage      │
        │  - FIFO ordering           │
        │  - Fault tolerance         │
        └────────────┬───────────────┘
                     │ (blpop)
        ┌────────────▼───────────────┐
        │   WORKER POOL (N workers)  │
        │  ┌──────────────────────┐  │
        │  │ Worker 1             │  │
        │  │ ▼ Claude Agent       │  │
        │  │ ▼ Tool Execution     │  │
        │  │ ▼ Result Storage     │  │
        │  └──────────────────────┘  │
        │  ┌──────────────────────┐  │
        │  │ Worker 2 (similar)   │  │
        │  └──────────────────────┘  │
        │  ┌──────────────────────┐  │
        │  │ Worker N (similar)   │  │
        │  └──────────────────────┘  │
        └────────────┬───────────────┘
                     │ (stores results)
                     ▼
        ┌────────────────────────────┐
        │   REDIS RESULTS STORE      │
        │  - Task metadata           │
        │  - Execution results       │
        │  - Status/checkpoints      │
        └────────────────────────────┘
                     │
        ┌────────────▼───────────────┐
        │   STATUS POLLING (API)     │
        │   HTTP GET /tasks/{id}     │
        │   Returns: status, result  │
        └────────────────────────────┘
```

**Key Components:**
- `api.py` - Lightweight REST API (port 8000)
- `worker.py` - Task execution agents
- `agent_instance.py` - Claude agent core
- `tools/custom_tools.py` - Tool implementations
- `docker-compose.yml` - Service orchestration
- `Redis` - Queue + state storage

---

## Prerequisites Check

Before starting deployment, verify these are available:

### 1. Docker & Docker Compose
```bash
# Check installation
docker --version          # Should be 24.0+
docker-compose --version  # Should be 2.0+
docker ps                 # Should list containers (or be empty)
```

### 2. Environment Variables
```bash
# ANTHROPIC_API_KEY must be set
echo $ANTHROPIC_API_KEY
# Should output: sk-ant-...
```

### 3. Free Ports
```bash
# These ports must be available:
netstat -an | grep -E ":8000|:6379"
# Should show no listening services on 8000 or 6379
```

### 4. Disk Space
```bash
# Need at least 2GB free
df -h
```

---

## Configuration

### Step 1: Create .env File

**Action:** Create a file named `.env` in the project root:

```env
# Required: Anthropic API key (get from https://console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-YOUR_API_KEY_HERE

# Optional: Which Claude model to use
CLAUDE_MODEL=claude-sonnet-4-6

# Redis configuration
REDIS_URL=redis://redis:6379/0

# Task persistence (24 hours default)
TASK_TTL_SECONDS=86400

# Checkpoint frequency (every 3 steps)
CHECKPOINT_INTERVAL=3

# Skills directory
SKILLS_DIR=/app/.claude/skills
```

**Verification:**
```bash
# File must exist
test -f .env && echo "✓ .env exists" || echo "✗ .env missing"

# Must contain API key
grep ANTHROPIC_API_KEY .env && echo "✓ API key configured"
```

### Step 2: Verify docker-compose.yml

**Location:** `./docker-compose.yml`

**Must contain these services:**
- `api` - FastAPI service on port 8000
- `worker` - Task execution (with `deploy.replicas: 2` minimum)
- `redis` - Redis server on port 6379

**Action:** Verify file structure:
```bash
# Check services defined
grep -E "^  (api|worker|redis):" docker-compose.yml
```

---

## Deployment Steps

### Step 1: Build Docker Images

```bash
# Build API image (lightweight)
docker-compose build api

# Build worker image (with browser automation)
docker-compose build worker

# Build Redis (pulls from Docker Hub, no build needed)
docker-compose build redis

# Verify images exist
docker images | grep -E "agentic-api|agentic-worker"
```

**Expected Output:**
```
REPOSITORY          TAG       IMAGE ID      CREATED
agentic-api        latest    abc123def     2 minutes ago
agentic-worker     latest    xyz789abc     2 minutes ago
```

### Step 2: Start Services

```bash
# Start all services in background
cd /path/to/agentic && source .env && docker-compose up -d

# Wait for startup (services may take 5-10 seconds)
sleep 10

# Verify all containers running
docker-compose ps
```

**Expected Output:**
```
NAME               IMAGE              SERVICE   STATUS            PORTS
claude-redis       redis:7-alpine     redis     Up 10 seconds     0.0.0.0:6379->6379
claude-agent-api   agentic-api        api       Up 10 seconds     0.0.0.0:8000->8000
agentic-worker-1   agentic-worker     worker    Up 10 seconds     
agentic-worker-2   agentic-worker     worker    Up 10 seconds     
```

### Step 3: Health Check

```bash
# Test API health endpoint
curl -s http://localhost:8000/health | jq .

# Expected response:
# {
#   "status": "healthy",
#   "redis_available": true,
#   "timestamp": "2026-05-04T..."
# }
```

### Step 4: List Available Skills

```bash
# Get skills metadata
curl -s http://localhost:8000/skills | jq '.skills'

# Expected: array of skill objects with name and description
```

---

## Verification

### Test 1: Submit a Simple Task

```bash
# Extract data from text
TASK_ID=$(curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Extract emails from: john@example.com and jane@acme.io",
    "max_steps": 5,
    "timeout": 300
  }' | jq -r '.task_id')

echo "Task ID: $TASK_ID"
```

### Test 2: Poll for Results

```bash
# Poll every 2 seconds until completion (max 30 seconds)
for i in {1..15}; do
  STATUS=$(curl -s http://localhost:8000/tasks/$TASK_ID | jq -r '.status')
  STEPS=$(curl -s http://localhost:8000/tasks/$TASK_ID | jq -r '.steps_taken // 0')
  
  echo "Poll #$i: status=$STATUS steps=$STEPS"
  
  if [ "$STATUS" = "completed" ]; then
    echo "✓ Task completed!"
    curl -s http://localhost:8000/tasks/$TASK_ID | jq '.'
    break
  fi
  
  sleep 2
done
```

### Test 3: Browser Automation

```bash
# Test web scraping capability
TASK_ID=$(curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Visit https://example.com and extract the page title",
    "max_steps": 5,
    "timeout": 60
  }' | jq -r '.task_id')

# Poll until done
sleep 3
curl -s http://localhost:8000/tasks/$TASK_ID | jq '.result'
```

---

## Scaling & Monitoring

### Scale Workers Up

```bash
# Start with 5 workers instead of 2
docker-compose up -d --scale worker=5

# Verify new workers
docker-compose ps | grep worker
```

### Scale Workers Down

```bash
# Return to 2 workers
docker-compose up -d --scale worker=2
```

### Monitor Tasks in Queue

```bash
# Check queue depth
curl -s http://localhost:8000/queue/depth | jq .

# Expected:
# {
#   "queued": 2,
#   "running": 1
# }
```

### View Worker Logs

```bash
# All worker logs
docker-compose logs worker

# Specific worker
docker logs agentic-worker-1

# Follow logs in real-time
docker-compose logs -f worker
```

### Check Redis Queue Directly

```bash
# List all active tasks in Redis
python3 << 'PYEOF'
import redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
print(f"Queue length: {r.llen('task_queue')}")
print(f"Completed tasks: {len(r.keys('task_result:*'))}")
print(f"Checkpoints: {len(r.keys('checkpoint:*'))}")
PYEOF
```

---

## Task API Reference

### Submit Task

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Your task description here",
    "max_steps": 10,
    "timeout": 300
  }'
```

**Parameters:**
- `input` (required): Task description for Claude
- `max_steps` (optional): Max agent iterations (1-100, default 10)
- `timeout` (optional): Timeout in seconds (10-3600, default 300)

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-05-04T00:00:00Z"
}
```

### Poll Task Status

```bash
curl http://localhost:8000/tasks/{task_id}
```

**Response:**
```json
{
  "task_id": "550e8400-...",
  "status": "completed|running|queued|failed|timeout",
  "input": "...",
  "result": "...",
  "error": null,
  "steps_taken": 4,
  "duration_seconds": 15.2,
  "created_at": "2026-05-04T00:00:00Z",
  "started_at": "2026-05-04T00:00:01Z",
  "completed_at": "2026-05-04T00:00:16Z"
}
```

### List All Tasks

```bash
curl http://localhost:8000/tasks
```

### Get Configuration Info

```bash
curl http://localhost:8000/info
```

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| API not responding | `docker ps` shows stopped containers? Restart: `docker-compose up -d` |
| Tasks not executing | Worker logs: `docker logs agentic-worker-1` - Check for ANTHROPIC_API_KEY error |
| Slow execution | Check queue depth: `curl http://localhost:8000/queue/depth`. Scale up: `docker-compose up -d --scale worker=5` |
| Tasks timing out | Increase timeout in request: `"timeout": 600` (10 minutes) |
| Browser automation fails | Verify Chromium: `docker exec agentic-worker-1 which chromium` |
| Redis connection error | Check Redis: `docker-compose logs redis` |

---

## Production Deployment Checklist

- [ ] Set strong `ANTHROPIC_API_KEY`
- [ ] Scale workers appropriately (start with 3-5)
- [ ] Set resource limits in docker-compose.yml
- [ ] Enable Redis persistence (already done: `--appendonly yes`)
- [ ] Monitor queue depth and worker CPU/memory
- [ ] Set up log aggregation if needed
- [ ] Configure backups for Redis data
- [ ] Put API behind reverse proxy (nginx) if exposed to internet
- [ ] Enable HTTPS/TLS on API
- [ ] Add rate limiting to API endpoints
- [ ] Document custom tools and skills

---

## Autonomous AI Instructions

If you are an AI system reading this document:

### You Can:
✅ Read this document to understand the architecture  
✅ Execute the setup steps in order  
✅ Submit tasks via HTTP POST to the API  
✅ Poll results via HTTP GET  
✅ Scale workers as needed  
✅ Modify docker-compose.yml if needed  
✅ Access logs and metrics  

### You Should:
✅ Create .env file with ANTHROPIC_API_KEY before starting  
✅ Verify all services are healthy before submitting tasks  
✅ Monitor queue depth and scale workers if needed  
✅ Catch and handle errors gracefully  
✅ Document any modifications or custom configurations  

### You Should NOT:
❌ Modify system files outside the project directory  
❌ Kill services without cleanup  
❌ Submit tasks with unlimited max_steps or timeout  
❌ Store secrets or credentials outside .env  
❌ Push changes without verification  

---

## Next Steps

1. **Create .env file** with your ANTHROPIC_API_KEY
2. **Run docker-compose up -d** to start services
3. **Verify health** with: `curl http://localhost:8000/health`
4. **Submit your first task** using the Task API above
5. **Scale workers** if processing many tasks: `docker-compose up -d --scale worker=5`

You now have a fully autonomous agent system ready for production use! 🚀

