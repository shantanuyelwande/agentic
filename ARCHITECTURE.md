# Architecture: Claude Managed Agents

A complete self-hosted agent system combining container isolation, Claude's intelligence, and custom tools.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Client/External System                       │
│                    (curl, Python, UI, etc.)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP REST API
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│           Orchestrator (FastAPI + Docker SDK)                    │
│                                                                   │
│  Responsibilities:                                               │
│  • Manage agent lifecycle (create, destroy)                      │
│  • Queue and dispatch tasks                                      │
│  • Monitor execution                                             │
│  • Coordinate volumes and resources                              │
│                                                                   │
│  Endpoints:                                                      │
│  • POST   /agents/create                                         │
│  • POST   /agents/{id}/task                                      │
│  • GET    /agents/{id}/status                                    │
│  • GET    /agents/{id}/logs                                      │
│  • DELETE /agents/{id}                                           │
│  • GET    /agents                                                │
│  • GET    /health                                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Docker API
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Agent Container  │ │ Agent Container  │ │ Agent Container  │
│      #1          │ │      #2          │ │      #N          │
│                  │ │                  │ │                  │
│ ┌──────────────┐ │ │ ┌──────────────┐ │ │ ┌──────────────┐ │
│ │ agent.py     │ │ │ │ agent.py     │ │ │ │ agent.py     │ │
│ │              │ │ │ │              │ │ │ │              │ │
│ │ • Reads task │ │ │ │ • Reads task │ │ │ │ • Reads task │ │
│ │ • Calls      │ │ │ │ • Calls      │ │ │ │ • Calls      │ │
│ │   Claude API │ │ │ │   Claude API │ │ │ │   Claude API │ │
│ │ • Executes   │ │ │ │ • Executes   │ │ │ │ • Executes   │ │
│ │   tools      │ │ │ │   tools      │ │ │ │   tools      │ │
│ │ • Saves      │ │ │ │ • Saves      │ │ │ │ • Saves      │ │
│ │   results    │ │ │ │   results    │ │ │ │   results    │ │
│ └──────────────┘ │ │ └──────────────┘ │ │ └──────────────┘ │
│                  │ │                  │ │                  │
│ ┌──────────────┐ │ │ ┌──────────────┐ │ │ ┌──────────────┐ │
│ │ /workspace   │ │ │ │ /workspace   │ │ │ │ /workspace   │ │
│ │ /memory      │ │ │ │ /memory      │ │ │ │ /memory      │ │
│ │ (volumes)    │ │ │ │ (volumes)    │ │ │ │ (volumes)    │ │
│ └──────────────┘ │ │ └──────────────┘ │ │ └──────────────┘ │
│                  │ │                  │ │                  │
│ Memory: 2GB      │ │ Memory: 2GB      │ │ Memory: 2GB      │
│ CPU: 1 core      │ │ CPU: 1 core      │ │ CPU: 1 core      │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

## Core Components

### 1. Orchestrator (orchestrator.py)

**Role**: Control plane for agent management

**Key Responsibilities**:
- Agent lifecycle management (create, terminate)
- Task submission and routing
- Container orchestration via Docker API
- Real-time monitoring and logging
- Status tracking

**Technologies**:
- FastAPI: REST API framework
- Docker SDK: Container management
- Pydantic: Request/response validation
- structlog: Structured logging

**In-Memory Registry**:
```python
agents: Dict[str, Dict[str, Any]] = {
    "agent-uuid": {
        "id": "agent-uuid",
        "name": "data-extractor",
        "container_id": "a3f5c2e...",
        "status": "ready",
        "created_at": "2026-04-28T...",
        "tasks": [
            {"task_id": "...", "status": "completed"},
            {"task_id": "...", "status": "running"}
        ],
        "volumes": {
            "workspace": "agent-uuid-ws",
            "memory": "agent-uuid-mem"
        }
    }
}
```

### 2. Agent Instance (agent_instance.py)

**Role**: The "brain" - runs inside isolated container

**Key Responsibilities**:
- Load task from `/workspace/task.json`
- Initialize Claude API client
- Implement agentic loop (Claude decides what tools to use)
- Execute custom tools
- Save results and persist session state

**Key Functions**:
- `run_agent()` - Main async loop
- `execute_tool()` - Tool invocation handler
- `load_skills_context()` - Load domain expertise
- `load_session_context()` - Restore previous state

**Execution Flow**:
```
Start Container
    ↓
Load task.json from /workspace
    ↓
Initialize Claude client
    ↓
Load skills + session context
    ↓
Loop (max 10 iterations):
    ├─ Call Claude API with task
    ├─ Process response:
    │  ├─ Extract text blocks → add to output
    │  ├─ Detect tool use → execute tool
    │  └─ Get tool results → continue loop
    └─ Stop if: end_turn or max iterations
    ↓
Save results to /workspace/output.json
    ↓
Update session.json in /memory
    ↓
Exit container
```

### 3. Custom Tools (tools/custom_tools.py)

**Role**: Domain-specific functions Claude can invoke

**Four Built-in Tools**:

1. **extract_structured_data()**
   - Extracts emails, phone numbers, URLs via regex
   - Use case: Data extraction from unstructured text

2. **query_database()**
   - Executes SQL queries safely
   - Prevents SQL injection
   - Use case: Database access

3. **call_external_api()**
   - Makes HTTP requests to whitelisted domains
   - Rate-limited
   - Use case: External API integration

4. **browse_web()** (NEW!)
   - Headless browser automation using Playwright/Chromium
   - Runs in isolated container, no GUI
   - Features: Navigation, clicking, form filling, screenshots, text extraction
   - Use case: Web scraping, form automation, dynamic content handling

**Tool Response Format**:
```python
{
    "content": [
        {
            "type": "text",
            "text": "Result as JSON or text"
        }
    ],
    "is_error": False  # True if tool failed
}
```

---

## Browser Automation Architecture

### Headless Browser in Containers

Each agent container includes:
- **Playwright**: Browser automation library
- **Chromium**: Headless browser engine
- **browser-use**: High-level browser agent

```
Agent Container
├─ Python 3.12
├─ Claude Agent (brain)
├─ Playwright
├─ Chromium (headless)
└─ Tools:
    ├─ extract_structured_data
    ├─ query_database
    ├─ call_external_api
    └─ browse_web ← Uses Playwright + Chromium

Browser runs headless (no GUI):
✅ Works in Docker (no display server)
✅ Lower memory (~200MB per browser)
✅ Faster execution
✅ Perfect for parallel tasks
```

### Browser Capabilities

When Claude calls `browse_web()`:
1. **Navigate**: Open websites, follow links
2. **Extract**: Get page HTML, text, links
3. **Interact**: Click buttons, fill forms, scroll
4. **Wait**: For JavaScript execution, dynamic content
5. **Screenshot**: Capture rendered page as PNG
6. **Generate Code**: Claude can generate Selenium/BeautifulSoup code

### Example Browser Task Flow

```
Client Request
    │
    ├─ Task: "Visit https://example.com and extract product data"
    │
    ▼
Claude receives task
    │
    ├─ Decides to use browse_web tool
    │
    ▼
Claude calls: browse_web({
    "url": "https://example.com",
    "task": "Extract product data",
    "extract_text": true,
    "extract_links": true,
    "screenshot": true
})
    │
    ▼
Agent Container:
    ├─ Launches headless Chromium
    ├─ Navigates to URL
    ├─ Executes JavaScript
    ├─ Waits for dynamic content
    ├─ Captures screenshot (PNG)
    ├─ Extracts page text
    ├─ Extracts links
    └─ Returns to Claude
    │
    ▼
Claude analyzes results:
    ├─ Sees page structure
    ├─ Sees extracted text
    ├─ Sees links
    ├─ Sees screenshot
    │
    ▼
Claude generates:
    ├─ Extracted data (JSON)
    ├─ Python scraping code (BeautifulSoup)
    ├─ Selenium automation code
    └─ Analysis/insights
    │
    ▼
Returns to Client
```

## Agent Lifecycle

### Phase 1: Creation

```bash
$ curl -X POST http://localhost:8000/agents/create \
  -d '{"name": "data-extractor"}'
```

**Orchestrator Actions**:
1. Generate unique agent ID
2. Create 2 Docker volumes:
   - `agent-{id}-ws` (workspace)
   - `agent-{id}-mem` (memory)
3. Start container from `claude-agent:latest` image
4. Set environment variables (AGENT_ID, API_KEY)
5. Mount volumes to `/workspace` and `/memory`
6. Store metadata in agent registry
7. Return agent_id to client

**Container Created**:
- Status: `running`
- Memory: 2GB limit
- CPU: 1 core limit
- Health check: every 30 seconds

### Phase 2: Task Submission

```bash
$ curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{"task": "Extract emails from...", "timeout": 300}'
```

**Orchestrator Actions**:
1. Validate agent exists
2. Create task structure with ID
3. Write task.json to container via Docker API:
   ```
   Create tar archive
   └─ task.json
   Copy to /workspace in container
   ```
4. Register task in agent's task list
5. Schedule background execution
6. Return task_id to client (async)

**Background Execution**:
- Scheduled immediately via FastAPI BackgroundTasks
- Agent container runs: `python /app/agent_instance.py`
- Agent reads `/workspace/task.json`
- Agent processes task using Claude + tools
- Agent writes `/workspace/output.json`
- Orchestrator detects completion when polling status

### Phase 3: Monitoring

```bash
$ curl http://localhost:8000/agents/{agent_id}/status
```

**Returns**:
- Agent metadata
- Container status (running/exited)
- Memory usage
- List of all tasks with statuses:
  - `submitted` → Task created, queued
  - `running` → Agent is processing
  - `completed` → Finished successfully
  - `failed` → Error occurred

**Client Polling Pattern**:
```python
for i in range(max_wait):
    status = get_status(agent_id)
    tasks = status["tasks"]
    
    for task in tasks:
        if task["task_id"] == target_task_id:
            if task["status"] == "completed":
                # Get output
                output = get_output(agent_id)
                break
            elif task["status"] == "failed":
                # Handle error
                break
    
    sleep(1)  # Poll every second
```

**Real-time Log Streaming**:
```bash
$ curl -N http://localhost:8000/agents/{agent_id}/logs
```

Server-Sent Events (SSE) stream:
```
data: [2026-04-28T...] Agent starting
data: [2026-04-28T...] Task received: extract emails
data: [2026-04-28T...] Calling Claude API
data: [2026-04-28T...] Tool: extract_structured_data
data: [2026-04-28T...] Tool result: found 3 emails
data: [2026-04-28T...] Agent completed
```

### Phase 4: Termination

```bash
$ curl -X DELETE http://localhost:8000/agents/{agent_id}
```

**Orchestrator Actions**:
1. Get container reference
2. Stop container (10-second timeout)
3. Remove container
4. Delete workspace volume
5. Delete memory volume
6. Remove from agent registry
7. Return confirmation

**Cleanup Guarantees**:
- All container processes stopped
- All volumes deleted
- All resources freed
- No orphaned containers/volumes

## Data Flow Patterns

### Task Execution Flow

```
Client Request
    │
    ├─ Write task.json to container
    │    └─ Via Docker API (tar archive)
    │
    ├─ Schedule background execution
    │    └─ FastAPI BackgroundTasks
    │
    └─ Return task_id immediately (async)
         
         [Background Process Starts]
              ↓
         Container: python agent_instance.py
              ↓
         Read /workspace/task.json
              ↓
         Initialize Claude client
              ↓
         Loop:
         ├─ Call Claude API
         ├─ Process response:
         │  ├─ Text blocks → output
         │  └─ Tool use → execute
         └─ Continue until end_turn
              ↓
         Write /workspace/output.json
              ↓
         Update /memory/session.json
              ↓
         Container exits
              ↓
         Orchestrator detects status change
```

### Volume Isolation Pattern

```
Host Machine
    │
    ├─ agent-uuid-1-ws (volume)
    │   └─ Mounted in container-1 at /workspace
    │       ├─ task.json (input)
    │       └─ output.json (result)
    │
    ├─ agent-uuid-1-mem (volume)
    │   └─ Mounted in container-1 at /memory
    │       └─ session.json (state)
    │
    ├─ agent-uuid-2-ws (volume)
    │   └─ Mounted in container-2 at /workspace
    │
    └─ agent-uuid-2-mem (volume)
        └─ Mounted in container-2 at /memory
```

**Benefits**:
- Data isolation: Container A can't access Container B's data
- Persistence: Data survives container restarts
- Parallelism: Agents don't interfere with each other

## Tool Execution Model

### How Claude Calls Tools

```
Orchestrator
    │
    ├─ Calls Claude API with task
    │
    ├─ Claude processes:
    │  └─ "I should use extract_structured_data tool"
    │
    ├─ Claude returns: tool_use block with:
    │  ├─ tool name: "extract_structured_data"
    │  ├─ tool input: {"text": "..."}
    │  └─ tool_use_id: "uuid"
    │
    ├─ Agent calls: execute_tool("extract_structured_data", {...})
    │
    ├─ Tool executes locally:
    │  └─ Validate input
    │  └─ Process request
    │  └─ Return results
    │
    └─ Loop back with tool result until end_turn
```

### Tool Response Contract

All tools must return:
```python
{
    "content": [
        {
            "type": "text",
            "text": "Result as JSON or text"
        }
    ],
    "is_error": False  # or True
}
```

## Error Handling

### Levels of Error Handling

**Level 1: Tool-level**
```python
def extract_structured_data(args):
    if not validate_input(args):
        return {
            "content": [{"type": "text", "text": "Error: invalid input"}],
            "is_error": True
        }
```

**Level 2: Agent-level**
```python
try:
    tool_result = await execute_tool(tool_name, tool_input)
except Exception as e:
    logger.error("tool_execution_error", error=str(e))
    result["status"] = "failed"
```

**Level 3: Orchestrator-level**
```python
try:
    container.exec_run("python agent_instance.py")
except Exception as e:
    logger.error("task_execution_error", error=str(e))
    task["status"] = "failed"
```

**Level 4: HTTP-level**
```python
if agent_id not in agents:
    raise HTTPException(status_code=404, detail="Agent not found")
```

## Security Model

### Container Isolation
- Each agent runs in separate container
- Separate volumes prevent data leakage
- Resource limits prevent DoS
- Network: containers can communicate only on `claude-network`

### Input Validation
- All HTTP inputs validated with Pydantic
- Tool inputs validated before execution
- SQL queries checked for dangerous patterns
- API calls limited to whitelisted domains

### Resource Limits
- Memory: 2GB per agent (configurable)
- CPU: 1 core per agent (configurable)
- Timeout: 10-3600 seconds per task
- Task execution: maximum 10 iterations

### Secret Management
- API keys passed via environment variables
- Never logged or printed
- Stored in `.env` (gitignored)
- Each container gets own API key

## Scaling Architecture

### Current State (Single Host)

```
Orchestrator (FastAPI)
├─ In-memory agent registry
├─ Local Docker daemon
└─ Synchronous request handling

Suitable for: 1-10 concurrent agents
```

### Production Scaling (Horizontal)

**Problem**: Single orchestrator is bottleneck

**Solution**: Distributed orchestrators with Redis

```
Load Balancer
    ├─ Orchestrator-1 ──┐
    ├─ Orchestrator-2   ├─ Redis (shared registry)
    └─ Orchestrator-N ──┘
        │
        └─ Docker Swarm / Kubernetes
            ├─ Agent-1
            ├─ Agent-2
            └─ Agent-N
```

**Changes Required**:
1. Replace in-memory `agents` dict with Redis
2. Add job queue (Redis or RabbitMQ)
3. Move task scheduling to queue workers
4. Add distributed locks for consistency

### Multi-Node Scaling (Kubernetes)

```
Kubernetes Cluster
    │
    ├─ Orchestrator Deployment (replicas: 3)
    │  └─ Shared Redis StatefulSet
    │
    ├─ Agent DaemonSet (or Job)
    │  ├─ Node-1: agents
    │  ├─ Node-2: agents
    │  └─ Node-N: agents
    │
    └─ Services
       ├─ Orchestrator API Service
       └─ Monitoring Stack (Prometheus/Grafana)
```

**Benefits**:
- Horizontal scaling: Add nodes, agents auto-spawn
- High availability: Orchestrator replicas handle failures
- Load balancing: Requests distributed
- Auto-recovery: Failed containers restart automatically

## Monitoring & Observability

### Structured Logging

All events logged as JSON:
```json
{
  "event": "task_submitted",
  "agent_id": "550e8400-...",
  "task_id": "8f3a1f4e-...",
  "timestamp": "2026-04-28T...",
  "duration_ms": 245
}
```

### Metrics to Track

- **Container Metrics**: CPU, memory, disk I/O
- **Task Metrics**: Success rate, duration, queue depth
- **System Metrics**: Active agents, total tasks, error rate
- **Business Metrics**: Cost per task, throughput, latency

### Log Aggregation

Current: Docker logs (available via `/logs` endpoint)

Production upgrade:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Datadog
- New Relic
- CloudWatch

## Extension Points

### Adding Custom Tools

```python
# 1. Define in tools/custom_tools.py
def my_tool(args: Dict) -> Dict:
    return {...}

# 2. Register in tools/__init__.py
from .custom_tools import my_tool
__all__ = ["my_tool"]

# 3. Claude discovers automatically
```

### Modifying Agent Behavior

Edit `agent_instance.py`:
- Change max iterations
- Add pre/post-processing
- Implement custom tool selection logic
- Add middleware (logging, filtering)

### Custom Orchestration

Extend `orchestrator.py`:
- Add authentication middleware
- Implement rate limiting
- Add custom routing logic
- Integrate with external systems

## Performance Characteristics

### Latency

- **Agent creation**: 2-5 seconds (pulling image, starting container)
- **Task submission**: <100ms (async, immediate return)
- **Task execution**: 5-300 seconds (depends on task complexity)
- **First Claude call**: 1-3 seconds (API latency)
- **Tool execution**: 100ms-10s (depends on tool)

### Throughput

- **Agents per host**: 10-50 (limited by memory, 2GB each)
- **Concurrent tasks**: Unlimited (queued)
- **Tasks per minute**: 60-600 (depends on task duration)

### Resource Usage

- **Orchestrator**: ~200MB memory, negligible CPU
- **Idle agent**: ~500MB memory, <1% CPU
- **Active agent**: 1.5-2GB memory, 50-100% CPU

## Comparison Matrix

| Feature | Daytona | LangChain Deep Agents | Our Implementation |
|---------|---------|----------------------|-------------------|
| Container isolation | ✅ | ❌ | ✅ |
| Managed agents | ✅ | ✅ | ✅ |
| Custom tools | ✅ | ✅ | ✅ |
| Claude SDK | ✅ | ⚠️ (LLM agnostic) | ✅ |
| Browser automation | ✅ | ❌ | ✅ |
| Self-hosted | ✅ | ✅ | ✅ |
| Job queue | ✅ | ❌ | ⚠️ (in-memory) |
| High availability | ✅ | ❌ | ⚠️ (single point) |
| Easy to extend | ⚠️ (proprietary) | ✅ | ✅ |

## References

- [Claude API Documentation](https://anthropic.com/docs)
- [Docker Container API](https://docs.docker.com/engine/api/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Daytona Architecture](https://github.com/daytonaio/daytona)
- [LangChain Deep Agents](https://www.langchain.com/blog/deep-agents-deploy-an-open-alternative-to-claude-managed-agents)

---

**Last Updated**: 2026-04-28  
**Status**: Production Ready
