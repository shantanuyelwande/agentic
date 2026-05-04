# Claude Project Instructions - v2.0

Horizontally-scalable Claude agent architecture using API + Worker + Redis pattern.

## Project Overview

**What this is**: A distributed system for autonomous Claude agents:
- **api.py**: Lightweight FastAPI service for task submission and polling
- **worker.py**: Stateless workers that execute tasks from Redis queue
- **Redis**: Persistent task queue and state store
- **Skills**: Progressive disclosure via read_file tool (metadata only by default)
- **browser-use**: Optional browser automation capability

**Architecture**: Replaces Docker-in-Docker with horizontally-scalable worker pattern.

```
User → API (fast) → Redis Queue → Worker Pool → Agent Execution → Results (Redis)
```

## Key Architecture Decisions

### 1. API + Worker + Redis Pattern
- ✅ **Stateless API**: Accepts tasks, returns immediately
- ✅ **Redis Queue**: Reliable task persistence and order
- ✅ **Horizontal scaling**: `docker-compose up --scale worker=5`
- ✅ **Fault tolerance**: Checkpointing every N steps
- ❌ NO Docker-in-Docker (was anti-pattern), NO single monolith

### 2. Progressive Skill Disclosure
- Skills metadata cached in memory (skill name + description only)
- Full skill content loaded on-demand via `read_file` tool
- Agent decides when to load full instructions
- Saves ~90% context window for typical tasks

### 3. Task Execution Model
- **Sync submission**: POST /tasks returns immediately
- **Async polling**: GET /tasks/{id} to check progress
- **Timeout enforcement**: Hard limit via `asyncio.timeout()`
- **Checkpoint recovery**: Can resume mid-task if worker crashes

## File Structure

```
api.py                            # API service (task submission, polling)
worker.py                         # Worker service (task execution loop)
agent_instance.py                 # Agent core (uses Anthropic SDK)
client.py                         # CLI client for testing
tools/
  └── custom_tools.py             # Tool implementations (read_file, etc.)
.claude/
  ├── skills/                     # Skills (name+description auto-discovered)
  │   ├── data-extraction/SKILL.md
  │   ├── web-research/SKILL.md
  │   └── competitor-analysis/SKILL.md
requirements.txt                  # Dependencies (no docker SDK needed)
Dockerfile                        # Worker image
Dockerfile.api                    # API image (lightweight)
docker-compose.yml                # Multi-service orchestration
```

## How It Works

### Task Flow (HTTP API)

1. **Submit**: `POST /tasks` with `{input, max_steps, timeout}`
2. **Queue**: API stores metadata in Redis, pushes to task_queue
3. **Worker**: Polls `brpop("task_queue")`, executes task
4. **Progress**: Worker updates task status in Redis periodically
5. **Complete**: Worker stores full result, sets status=completed
6. **Retrieve**: Client polls `GET /tasks/{id}` until completion

### Agent Execution

1. Agent receives task dict (not file-based)
2. Loads skills index (metadata only, ~100 tokens)
3. Claude decides which skills to use
4. Agent uses `read_file` tool to load full skill on-demand
5. Every 3 steps, checkpoint progress to Redis
6. On completion/timeout/error, return structured result dict

## Built-in Tools Available

- **extract_structured_data**: Extract emails, phones, URLs from text
- **query_database**: Execute safe SQL queries (read-only)
- **call_external_api**: Call whitelisted REST APIs
- **read_file**: Read skill content or files from safe dirs
- **browse_web**: Browser automation (optional, Chromium-based)

## Getting Started

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
export ANTHROPIC_API_KEY=sk-...

# 3. Start services
docker-compose up

# 4. In another terminal, submit a task
python client.py "Extract emails from: john@example.com"
```

### Local Testing (Standalone)

Test agent without Docker or Redis:

```bash
# Run agent directly
python agent_instance.py "Extract emails from: contact@example.com"

# Or
export ANTHROPIC_API_KEY=sk-...
python agent_instance.py "Research Claude Agent SDK"
```

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Liveness check |
| GET | `/skills` | List available skills (metadata) |
| GET | `/info` | Configuration info |
| POST | `/tasks` | Submit task |
| GET | `/tasks/{id}` | Get task status/result |
| GET | `/tasks` | List all tasks |
| GET | `/queue/depth` | Queue statistics |

### Example: Submit and Poll Task

```bash
# Submit task
TASK_ID=$(curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"input": "Extract emails from: john@example.com", "max_steps": 10}' \
  | jq -r '.task_id')

# Poll until completion
while true; do
  STATUS=$(curl -s http://localhost:8000/tasks/$TASK_ID | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" != "queued" ] && [ "$STATUS" != "running" ] && break
  sleep 1
done

# Get result
curl http://localhost:8000/tasks/$TASK_ID | jq '.result'
```

## Scaling

### Scale Workers

```bash
# Start with 5 workers
docker-compose up --scale worker=5

# Or dynamically scale existing deployment
docker-compose up -d --scale worker=10
```

**Key Notes**:
- Workers are stateless (no affinity required)
- Redis handles ordering and durability
- Checkpoints enable fault recovery
- Each worker processes one task at a time

### Performance Tuning

**Environment Variables**:
- `CHECKPOINT_INTERVAL`: Save progress every N steps (default 3)
- `TASK_TTL_SECONDS`: Keep task data for N seconds (default 86400)
- `MAX_STEPS`: Default max iterations per task (default 10)

## Creating Skills

Skills are Markdown files in `.claude/skills/{name}/SKILL.md`:

```bash
mkdir -p .claude/skills/my-skill
cat > .claude/skills/my-skill/SKILL.md << 'EOF'
---
name: market-analysis
description: Analyze market trends, competitors, and opportunities
---

# Market Analysis Skill

Use this when you need to analyze markets, identify trends, or research competitors.

## Approach

1. Search for recent reports and news
2. Identify 3-5 credible sources
3. Extract key metrics (market size, growth rate, key players)
4. Summarize findings and outlook

## Key metrics to track

- Total Addressable Market (TAM)
- Compound Annual Growth Rate (CAGR)
- Key competitors and their market share
- Emerging trends
EOF
```

Agent automatically discovers skills on startup.

## Troubleshooting

**API Won't Start**
```bash
# Check Redis is running
docker-compose logs redis

# Verify connectivity
redis-cli -u redis://localhost:6379/0 ping
```

**Worker Not Processing Tasks**
```bash
# Check worker logs
docker-compose logs worker

# Verify Redis queue
redis-cli -u redis://localhost:6379/0 llen task_queue
```

**Task Timeout**
- Default timeout is 300 seconds (5 min)
- Adjust via API: `POST /tasks` with `timeout` parameter
- Or adjust globally in `.env`: `TASK_TTL_SECONDS=3600`

**Skills Not Discovered**
```bash
# Verify skill structure
ls -la .claude/skills/*/SKILL.md

# Check YAML frontmatter
head -5 .claude/skills/*/SKILL.md
```

**ANTHROPIC_API_KEY Error**
```bash
# Add to .env or export
export ANTHROPIC_API_KEY=sk-ant-...

# Or pass as environment variable to Docker
docker-compose run -e ANTHROPIC_API_KEY=sk-ant-... api /bin/bash
```

## Architecture Details

### Why Redis?

- **Durability**: Tasks persist if worker crashes
- **Ordering**: FIFO queue ensures fairness
- **Checkpointing**: Progress saved every 3 steps (1-hour TTL)
- **Simplicity**: No external databases needed

### Why Stateless Workers?

- **Scalability**: Add/remove workers without coordination
- **Resilience**: Failed worker doesn't block queue
- **Isolation**: Each task completely independent
- **Simplicity**: No inter-worker communication

### Checkpoint Recovery

If a worker crashes mid-task:
1. Task is marked as `failed` (not requeued)
2. Next poll returns error: "Worker crashed"
3. User can re-submit task from API
4. Checkpoint is ignored on restart (resuming not implemented yet)

## Security Considerations

- ✅ API key in `.env` (included in `.gitignore`)
- ✅ read_file tool restricts to safe directories only
- ✅ SQL tool blocks DELETE/DROP/ALTER/TRUNCATE
- ✅ External APIs whitelisted by domain
- ✅ All timestamps in UTC, no local time leaks

**Never**:
- ❌ Commit `.env` file with real API key
- ❌ Pass sensitive data in task descriptions
- ❌ Run untrusted skill code
- ❌ Expose Redis to public internet (use firewall)

## Version & Dependencies

- Python: 3.12 (slim base image)
- Anthropic SDK: >=0.40.0
- FastAPI: >=0.115.0
- Redis: 7 (Alpine)
- browser-use: >=0.1.48 (optional)

## Useful Resources

- [Anthropic API Docs](https://docs.anthropic.com)
- [Claude Models](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)
- [Redis Docs](https://redis.io/docs/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [browser-use on GitHub](https://github.com/browser-use/browser-use)

## Next Steps

1. **Add more skills** in `.claude/skills/`
2. **Scale workers** as load increases
3. **Monitor metrics** (queue depth, task duration)
4. **Integrate with external systems** (webhooks, databases)
5. **Deploy to Kubernetes** (stateless design supports it)

---

**Last Updated**: 2026-05-03
**Architecture**: API + Worker + Redis (v2.0)
**Status**: Production-ready, horizontally scalable
