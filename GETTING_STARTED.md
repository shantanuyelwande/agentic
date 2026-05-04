# Getting Started with Agentic

A fast, production-ready agent system using Claude API + Redis + Docker Compose.

## ⚡ 5-Minute Setup

### Step 1: Create .env

```bash
cp .env.example .env

# Edit .env and add your API key:
# ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
```

### Step 2: Build & Start

```bash
# Build Docker images
docker-compose build

# Start all services (API + 2 workers + Redis)
docker-compose up -d

# Wait for startup
sleep 5

# Verify health
curl http://localhost:8000/health
# Should return: {"status": "healthy", ...}
```

### Step 3: Submit Your First Task

```bash
# Submit a task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Extract emails from: john@example.com and jane@acme.io",
    "max_steps": 5
  }' | jq .

# Save the task_id from response
# Example: "task_id": "550e8400-e29b-41d4-a716-446655440000"
```

### Step 4: Check Results

```bash
# Poll for status (replace {task_id} with actual ID)
curl http://localhost:8000/tasks/{task_id} | jq .

# Response includes:
# - status: "queued" | "running" | "completed" | "failed"
# - result: The agent's output
# - steps_taken: Number of iterations
# - duration_seconds: Execution time
```

---

## 📚 Common Tasks

### Extract Data from Text

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Extract all phone numbers from: Call us at 555-123-4567 or 555-987-6543",
    "max_steps": 5
  }' | jq -r '.task_id'

# Then poll the task_id
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

---

## 🔧 Scale Workers

The system starts with **2 workers**. Scale up for more throughput:

```bash
# Scale to 5 workers
docker-compose up -d --scale worker=5

# Verify
docker-compose ps | grep worker

# Scale back down
docker-compose up -d --scale worker=2
```

---

## 📊 Monitor System

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

---

## 🔐 Tool Access

Workers have access to 5 built-in tools:

| Tool | Purpose | Example |
|------|---------|---------|
| `extract_structured_data` | Extract emails, phones, URLs | `"Extract emails from: john@example.com"` |
| `query_database` | SQL SELECT queries | `"SELECT * FROM sample LIMIT 10"` |
| `call_external_api` | Call REST APIs (whitelisted) | `"Get https://jsonplaceholder.typicode.com/users"` |
| `read_file` | Read files from safe dirs | Automatically used to load skills |
| `browse_web` | Web scraping + automation | `"Visit https://example.com and extract..."` |

---

## 🎓 API Reference

### Submit Task

```bash
POST /tasks
Content-Type: application/json

{
  "input": "Your task description here",
  "max_steps": 10,        # Optional (1-100, default 10)
  "timeout": 300          # Optional (10-3600s, default 300)
}

Response:
{
  "task_id": "550e8400-...",
  "status": "queued",
  "created_at": "2026-05-04T..."
}
```

### Poll Status

```bash
GET /tasks/{task_id}

Response:
{
  "task_id": "550e8400-...",
  "status": "queued|running|completed|failed|timeout",
  "input": "...",
  "result": "Agent output here",
  "error": null,
  "steps_taken": 4,
  "duration_seconds": 15.2,
  "created_at": "2026-05-04T...",
  "started_at": "2026-05-04T...",
  "completed_at": "2026-05-04T..."
}
```

### Health Check

```bash
GET /health

Response:
{
  "status": "healthy",
  "redis_available": true,
  "timestamp": "2026-05-04T..."
}
```

### List Skills

```bash
GET /skills

Response:
{
  "count": 3,
  "skills": [
    {
      "name": "data-extraction",
      "description": "Extract structured data..."
    },
    ...
  ]
}
```

---

## 🛠️ Add Custom Tools

Edit `tools/custom_tools.py`:

```python
def my_custom_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """My custom tool for Claude to use."""
    
    # Get input
    my_param = args.get("my_param", "")
    
    # Validate
    if not my_param:
        return {
            "content": [{"type": "text", "text": "Error: my_param required"}],
            "is_error": True
        }
    
    # Process
    result = do_something(my_param)
    
    # Return
    return {
        "content": [{"type": "text", "text": json.dumps(result)}]
    }
```

Then register in `agent_instance.py` in the tools array.

Claude will discover it automatically!

---

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

---

## 📖 Next Steps

1. **Read CLAUDE.md** - Architecture & design decisions
2. **Read SETUP_AUTONOMOUS.md** - For AI systems setting up autonomously
3. **Check SKILLS.md** - How to create custom skills
4. **Read CONTRIBUTING.md** - Contributing guidelines

---

## ✅ What You Have Now

- ✅ Fast REST API on port 8000
- ✅ Worker pool (default 2, scalable)
- ✅ Redis queue & state store
- ✅ 5 built-in tools
- ✅ Browser automation
- ✅ Fault tolerance & checkpointing
- ✅ Task logging & monitoring

**You're ready to process tasks!** 🚀

---

## 🎯 Example Workflow

```bash
#!/bin/bash

# 1. Submit a complex task
TASK_ID=$(curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Visit deeplearning.ai and find 3 free short courses",
    "max_steps": 10,
    "timeout": 60
  }' | jq -r '.task_id')

echo "Submitted task: $TASK_ID"

# 2. Poll until done
while true; do
  STATUS=$(curl -s http://localhost:8000/tasks/$TASK_ID | jq -r '.status')
  echo "Status: $STATUS"
  
  if [ "$STATUS" = "completed" ]; then
    # 3. Get results
    curl -s http://localhost:8000/tasks/$TASK_ID | jq '.result'
    break
  fi
  
  sleep 2
done
```

---

**Questions?** Check README.md or SETUP_AUTONOMOUS.md.

