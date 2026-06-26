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

---

## Daily Market Advisory Routine

### Log Storage & Continuity

Daily market advisory logs are stored in `market-advisory/logs/` with filenames `YYYY-MM-DD.md`.

**BEFORE generating any new advisory, the routine MUST:**

1. **Read the last 7 calendar days of logs** from `market-advisory/logs/` using the GitHub MCP tool `get_file_contents` on the `shantanuyelwande/agentic` repo (branch: `claude/epic-curie-exldve`). Calculate the date range (today minus 7 days) and attempt to read each file. Missing files (weekends/holidays) are expected — skip them silently.

2. **Open Recommendations Check** — For every BUY NOW / ACCUMULATE call found in the prior logs:
   - Look up the current price of the stock
   - Compare to the price at time of recommendation
   - Determine if the call is still valid or has been invalidated (check the stated invalidation conditions)
   - Output updated action: hold, add more, cut, or exit
   - Flag any invalidated recommendations explicitly

3. **Trend Detection** — Compare macro indicators across the last week of logs:
   - Is the 10-yr yield trending up or down?
   - Is VIX rising or falling?
   - Are portfolio stocks continuing to decline or stabilizing?
   - Has oil direction changed?
   - Use this to inform whether current recommendations should be more aggressive or more cautious than prior days.

4. **Position Sizing Continuity** — If a prior log recommended "deploy 25% of intended allocation," today's log should NOT re-recommend the full entry. Instead, recommend the NEXT tranche (e.g., "deploy another 25%") or state "hold — waiting for [trigger]."

### Saving the Daily Log

After completing the advisory analysis, the routine MUST:

1. **Generate the log file** in the standard format (see `market-advisory/README.md` for the template sections).
2. **Save it via GitHub MCP** using `create_or_update_file` to `market-advisory/logs/YYYY-MM-DD.md` on branch `claude/epic-curie-exldve` in the `shantanuyelwande/agentic` repo.
3. **The log must include ALL sections:** Macro Snapshot, Macro Gate, News Events, Open Recommendations Check (with prior call validation), Portfolio Analysis (each stock with label + dip type + invalidation), Proactive Suggestions, Calendar, Action Summary.

### Email Delivery

After saving the log, send a formatted HTML email to `shantanu.y@gmail.com` via the Gmail MCP `create_draft` tool with the full advisory content.

### Portfolio Tracked

| Ticker | Name |
|--------|------|
| META | Meta Platforms |
| AAPL | Apple |
| AMZN | Amazon |
| GOOGL | Alphabet |
| MSFT | Microsoft |
| NVDA | Nvidia |
| VOO | Vanguard S&P 500 ETF |

---

## Key Architecture Decisions

### 1. API + Worker + Redis Pattern
- Stateless API: Accepts tasks, returns immediately
- Redis Queue: Reliable task persistence and order
- Horizontal scaling: `docker-compose up --scale worker=5`
- Fault tolerance: Checkpointing every N steps

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
market-advisory/
  ├── README.md                   # Log format docs & template
  └── logs/                       # Daily advisory logs (YYYY-MM-DD.md)
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

## Scaling

### Scale Workers

```bash
docker-compose up --scale worker=5
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

Skills are Markdown files in `.claude/skills/{name}/SKILL.md`. Agent automatically discovers skills on startup.

## Troubleshooting

**API Won't Start**
```bash
docker-compose logs redis
redis-cli -u redis://localhost:6379/0 ping
```

**Worker Not Processing Tasks**
```bash
docker-compose logs worker
redis-cli -u redis://localhost:6379/0 llen task_queue
```

**Task Timeout**
- Default timeout is 300 seconds (5 min)
- Adjust via API: `POST /tasks` with `timeout` parameter

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

## Security Considerations

- API key in `.env` (included in `.gitignore`)
- read_file tool restricts to safe directories only
- SQL tool blocks DELETE/DROP/ALTER/TRUNCATE
- External APIs whitelisted by domain
- All timestamps in UTC, no local time leaks

## Version & Dependencies

- Python: 3.12 (slim base image)
- Anthropic SDK: >=0.40.0
- FastAPI: >=0.115.0
- Redis: 7 (Alpine)
- browser-use: >=0.1.48 (optional)

---

**Last Updated**: 2026-06-26
**Architecture**: API + Worker + Redis (v2.0)
**Status**: Production-ready, horizontally scalable
