# Orchestrator Guide: Deep Dive for Developers

This guide explains how the orchestrator works internally, how to extend it, and how to debug issues.

**Audience**: Developers who need to understand, modify, or scale the system.

## File Structure

```
orchestrator.py (380 lines)
├── Configuration
│   ├── DOCKER_IMAGE - Container image to run
│   ├── AGENTS_DIR - Persistent data directory
│   └── docker_client - Connection to Docker daemon
│
├── Pydantic Models
│   ├── CreateAgentRequest - Schema for create endpoint
│   ├── TaskRequest - Schema for task submission
│   ├── AgentInfo - Schema for agent data
│   └── TaskResult - Schema for task result
│
├── Helper Functions
│   ├── get_docker_client() - Docker connection with error handling
│   ├── write_task_to_container() - Write task.json via Docker API
│   └── execute_task_in_container() - Background task execution
│
└── API Endpoints (7 total)
    ├── GET  /health
    ├── POST /agents/create
    ├── POST /agents/{id}/task
    ├── GET  /agents/{id}/status
    ├── GET  /agents/{id}/logs
    ├── DELETE /agents/{id}
    └── GET  /agents
```

## The Agent Registry

### Data Structure

```python
agents: Dict[str, Dict[str, Any]] = {
    "550e8400-e29b-41d4-a716-446655440000": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "data-extractor",
        "container_id": "a3f5c2e9d1a4b2c6e8f0...",  # Full Docker ID
        "status": "ready",  # ready | error
        "created_at": "2026-04-28T12:34:56.789Z",
        "tasks": [
            {
                "task_id": "8f3a1f4e-...",
                "status": "submitted",  # submitted | running | completed | failed
                "created_at": "2026-04-28T12:35:00.000Z",
                "completed_at": null,  # Set when done
                "error": null  # Set if failed
            },
            {
                "task_id": "9g4b2f5f-...",
                "status": "completed",
                "created_at": "2026-04-28T12:35:05.000Z",
                "completed_at": "2026-04-28T12:35:25.000Z",
                "error": null
            }
        ],
        "volumes": {
            "workspace": "agent-550e8400-ws",
            "memory": "agent-550e8400-mem"
        }
    }
}
```

### Important Notes

- **In-Memory**: Stored in process memory (lost on restart)
- **Production**: Should use Redis or database
- **Thread-Safe**: Not protected by locks (single-threaded FastAPI)
- **Cleanup**: Manually delete volumes during termination

## Endpoint Deep Dive

### 1. POST /agents/create

**HTTP Request**:
```bash
POST /agents/create HTTP/1.1
Content-Type: application/json

{
  "name": "data-extractor",
  "config": {}  # optional
}
```

**Pydantic Model**:
```python
class CreateAgentRequest(BaseModel):
    name: Optional[str] = Field(None, description="Agent name")
    config: Optional[Dict[str, Any]] = Field(None, description="Agent configuration")
```

**Code Flow**:

```python
async def create_agent(request: CreateAgentRequest):
    client = get_docker_client()  # Get Docker client, raise if not available
    
    agent_id = str(uuid.uuid4())  # Generate unique ID
    logger.info("creating_agent", agent_id=agent_id, agent_name=request.name)
    
    try:
        # Step 1: Create volumes
        ws_volume = client.volumes.create(name=f"agent-{agent_id}-ws")
        mem_volume = client.volumes.create(name=f"agent-{agent_id}-mem")
        # These are Docker named volumes that persist data
        
        # Step 2: Start container
        container = client.containers.run(
            DOCKER_IMAGE,  # "claude-agent:latest"
            detach=True,   # Start in background, don't wait
            name=f"agent-{agent_id[:8]}",  # Short name for convenience
            environment={
                "AGENT_ID": agent_id,
                "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
            },
            volumes={
                ws_volume.name: {"bind": "/workspace", "mode": "rw"},
                mem_volume.name: {"bind": "/memory", "mode": "rw"},
            },
            mem_limit="2g",  # Hard memory limit
            cpus=1.0,        # CPU cores
            healthcheck={
                "test": ["CMD", "python", "-c", "import sys; sys.exit(0)"],
                "interval": 30,
                "timeout": 10,
                "retries": 3,
            },
        )
        
        # Step 3: Store metadata
        agents[agent_id] = {
            "id": agent_id,
            "name": request.name or f"agent-{agent_id[:8]}",
            "container_id": container.id,
            "status": "ready",
            "created_at": datetime.now().isoformat(),
            "tasks": [],
            "volumes": {
                "workspace": ws_volume.name,
                "memory": mem_volume.name,
            }
        }
        
        # Step 4: Return response
        return {
            "agent_id": agent_id,
            "name": agents[agent_id]["name"],
            "status": "created",
            "container_id": container.id[:12],  # Shortened ID
            "created_at": agents[agent_id]["created_at"],
        }
```

**Key Implementation Details**:
- Uses `uuid.uuid4()` for uniqueness
- Creates 2 named volumes (not mapped to host directories)
- Sets `detach=True` to start container and return immediately
- Passes AGENT_ID to container so it knows its identity
- Passes API_KEY to container for Claude authentication
- Sets resource limits (2GB memory, 1 CPU core)
- Healthcheck pings container every 30 seconds

**Docker API Used**:
```python
# Create volume
volume = docker_client.volumes.create(name="...")

# Start container
container = docker_client.containers.run(
    image, detach=True, volumes={...}, environment={...}, ...
)

# container.id is full ID: "a3f5c2e9d1a4b2c6e8f012345678901234567890"
# container.id[:12] is short ID: "a3f5c2e9d1a4"
```

---

### 2. POST /agents/{agent_id}/task

**HTTP Request**:
```bash
POST /agents/550e8400-e29b-41d4-a716-446655440000/task HTTP/1.1
Content-Type: application/json

{
  "task": "Extract emails from: john@example.com, 555-123-4567",
  "timeout": 300
}
```

**Pydantic Model**:
```python
class TaskRequest(BaseModel):
    task: str = Field(..., description="Task description for Claude")
    timeout: int = Field(300, description="Task timeout in seconds", ge=10, le=3600)
```

**Code Flow**:

```python
async def submit_task(
    agent_id: str, 
    request: TaskRequest, 
    background_tasks: BackgroundTasks  # FastAPI's background task manager
):
    # Step 1: Validate agent exists
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    agent = agents[agent_id]
    task_id = str(uuid.uuid4())
    
    logger.info("submitting_task", agent_id=agent_id, task_id=task_id)
    
    try:
        # Step 2: Get running container
        container = docker_client.containers.get(agent["container_id"])
        # Verify container is actually running
        
        # Step 3: Create task data structure
        task_data = {
            "task_id": task_id,
            "task": request.task,
            "timeout": request.timeout,
        }
        
        # Step 4: Write task.json to container's /workspace
        write_task_to_container(container, task_data)
        # This uses Docker's copy API, not shared filesystem
        
        # Step 5: Register task in agent's task list
        agents[agent_id]["tasks"].append({
            "task_id": task_id,
            "status": "submitted",  # Not "running" yet
            "created_at": datetime.now().isoformat(),
        })
        
        # Step 6: Schedule background execution (returns immediately)
        background_tasks.add_task(
            execute_task_in_container,
            agent_id,
            task_id,
            container,  # Pass container object for background use
        )
        
        logger.info("task_scheduled", agent_id=agent_id, task_id=task_id)
        
        # Step 7: Return to client immediately (async)
        return {
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "submitted",
            "created_at": datetime.now().isoformat(),
        }
```

**Background Execution** (in `execute_task_in_container`):

```python
async def execute_task_in_container(
    agent_id: str,
    task_id: str,
    container,  # Container object passed from submit_task
) -> None:
    """This runs in background, doesn't block client."""
    logger.info("executing_task_in_background", agent_id=agent_id, task_id=task_id)
    
    try:
        # Execute the agent script inside the container
        exit_code, output = container.exec_run(
            "python /app/agent_instance.py",  # Run this inside container
            stdout=True,
            stderr=True,
            demux=False,  # Combine stdout/stderr
        )
        
        logger.info(
            "task_executed",
            agent_id=agent_id,
            task_id=task_id,
            exit_code=exit_code
        )
        
        # Update task status in registry
        if agent_id in agents:
            for task in agents[agent_id]["tasks"]:
                if task["task_id"] == task_id:
                    task["status"] = "completed" if exit_code == 0 else "failed"
                    task["completed_at"] = datetime.now().isoformat()
                    break
    
    except Exception as e:
        logger.error("task_execution_error", error=str(e))
        if agent_id in agents:
            for task in agents[agent_id]["tasks"]:
                if task["task_id"] == task_id:
                    task["status"] = "failed"
                    task["error"] = str(e)
                    break
```

**Write Task to Container** (helper function):

```python
def write_task_to_container(container, task_data: Dict[str, Any]) -> None:
    """Write task.json to container via Docker API."""
    import tarfile
    import io
    
    # Convert task to JSON bytes
    task_json = json.dumps(task_data, indent=2).encode()
    
    # Create tar archive (Docker API requires tar format)
    info = tarfile.TarInfo(name="task.json")
    info.size = len(task_json)
    
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(task_json))
    
    tar_buffer.seek(0)
    
    # Copy tar archive to container's /workspace directory
    container.put_archive("/workspace", tar_buffer.getvalue())
    # Result: /workspace/task.json inside container
```

**Key Implementation Details**:
- Returns immediately to client (async background execution)
- Uses FastAPI's `BackgroundTasks` for scheduling
- Container executes agent script with `exec_run()`
- Task status persists in agent registry
- If container disconnects, background task continues until completion

**Docker API Used**:
```python
# Get running container
container = docker_client.containers.get(container_id)

# Execute command in running container
exit_code, output = container.exec_run(
    "python /app/agent_instance.py",
    stdout=True, stderr=True
)

# Copy files to container
container.put_archive("/workspace", tar_data)
```

---

### 3. GET /agents/{agent_id}/status

**HTTP Request**:
```bash
GET /agents/550e8400-e29b-41d4-a716-446655440000/status HTTP/1.1
```

**Code Flow**:

```python
async def get_agent_status(agent_id: str):
    # Step 1: Validate agent exists
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    agent = agents[agent_id]
    
    try:
        # Step 2: Get live container stats
        container = docker_client.containers.get(agent["container_id"])
        container.reload()  # Refresh container metadata
        
        # Get container statistics
        stats = container.stats(stream=False)  # Single snapshot
        # stats = {
        #     "memory_stats": {
        #         "usage": 1048576,  # bytes
        #         ...
        #     },
        #     ...
        # }
        
        memory_usage_mb = stats["memory_stats"]["usage"] / (1024 * 1024)
        
        # Step 3: Return comprehensive status
        return {
            "agent_id": agent_id,
            "name": agent["name"],
            "status": agent["status"],
            "container_status": container.status,  # running | exited | paused
            "created_at": agent["created_at"],
            "tasks": agent["tasks"],  # All tasks with statuses
            "memory_usage_mb": round(memory_usage_mb, 2),
        }
    
    except Exception as e:
        logger.error("status_check_failed", error=str(e))
        # Return partial status even if container is gone
        return {
            "agent_id": agent_id,
            "error": str(e),
            "tasks": agent.get("tasks", []),
        }
```

**Key Implementation Details**:
- Checks live container status (not just registry)
- Returns memory usage in MB
- Gracefully handles container not found errors
- Always returns task list (even if container is dead)
- `container.reload()` refreshes metadata from Docker daemon

**Response Example**:
```json
{
  "agent_id": "550e8400-...",
  "name": "data-extractor",
  "status": "ready",
  "container_status": "running",
  "created_at": "2026-04-28T12:34:56Z",
  "memory_usage_mb": 512.5,
  "tasks": [
    {
      "task_id": "8f3a1f4e-...",
      "status": "completed",
      "created_at": "2026-04-28T12:35:00Z",
      "completed_at": "2026-04-28T12:35:25Z"
    }
  ]
}
```

---

### 4. GET /agents/{agent_id}/logs

**HTTP Request**:
```bash
GET /agents/550e8400-e29b-41d4-a716-446655440000/logs HTTP/1.1
# Connection stays open, logs stream in real-time
```

**Code Flow**:

```python
@app.get("/agents/{agent_id}/logs")
async def stream_logs(agent_id: str):
    # Step 1: Validate agent
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    agent = agents[agent_id]
    
    try:
        # Step 2: Get container
        container = docker_client.containers.get(agent["container_id"])
        
        # Step 3: Create async generator that streams logs
        async def log_generator():
            try:
                # Get logs from container (stream=True means follow)
                for log in container.logs(stream=True, follow=True):
                    # Convert bytes to string and format as SSE
                    yield f"data: {log.decode('utf-8')}\n\n"
            except Exception as e:
                yield f"data: Error streaming logs: {str(e)}\n\n"
        
        # Step 4: Return streaming response
        return StreamingResponse(log_generator(), media_type="text/event-stream")
    
    except Exception as e:
        logger.error("log_stream_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to stream logs: {str(e)}")
```

**Server-Sent Events Format**:
```
data: [2026-04-28T12:35:00] Agent starting
data: [2026-04-28T12:35:01] Loading task.json
data: [2026-04-28T12:35:02] Initializing Claude API
data: [2026-04-28T12:35:03] Calling Claude API
data: [2026-04-28T12:35:05] Tool use: extract_structured_data
data: [2026-04-28T12:35:06] Tool result: found 3 emails
data: [2026-04-28T12:35:07] Task completed
```

**Client Usage**:
```python
# Python
async with client.stream("GET", f"/agents/{agent_id}/logs") as response:
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            print(line[6:])

# Bash with curl
curl -N http://localhost:8000/agents/{agent_id}/logs

# JavaScript
const response = await fetch(`/agents/${agent_id}/logs`);
const reader = response.body.getReader();
// Process stream...
```

**Key Implementation Details**:
- Uses `StreamingResponse` for real-time data
- SSE format: "data: " prefix + content + "\n\n"
- `follow=True` keeps logs coming as container runs
- Works even if container has already exited (gets history)

---

### 5. DELETE /agents/{agent_id}

**HTTP Request**:
```bash
DELETE /agents/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
```

**Code Flow**:

```python
async def terminate_agent(agent_id: str):
    # Step 1: Validate agent exists
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    agent = agents[agent_id]
    logger.info("terminating_agent", agent_id=agent_id)
    
    try:
        # Step 2: Stop and remove container
        container = docker_client.containers.get(agent["container_id"])
        container.stop(timeout=10)  # Wait up to 10s for graceful shutdown
        container.remove(force=True)  # Force remove if stuck
        logger.info("container_removed", agent_id=agent_id)
        
        # Step 3: Remove volumes (this deletes data permanently!)
        for vol_name in agent["volumes"].values():
            try:
                volume = docker_client.volumes.get(vol_name)
                volume.remove()
                logger.info("volume_removed", agent_id=agent_id, volume=vol_name)
            except Exception as e:
                # Log but don't fail if volume already deleted
                logger.warning("volume_removal_failed", volume=vol_name, error=str(e))
        
        # Step 4: Delete from registry
        del agents[agent_id]
        logger.info("agent_terminated", agent_id=agent_id)
        
        # Step 5: Return confirmation
        return {
            "status": "terminated",
            "agent_id": agent_id,
            "terminated_at": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error("termination_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to terminate agent: {str(e)}")
```

**Cleanup Sequence**:
1. Get container reference
2. Stop container (SIGTERM, then SIGKILL if needed)
3. Remove container from Docker
4. Remove workspace volume (task.json, output.json deleted)
5. Remove memory volume (session.json deleted)
6. Remove from agent registry

**Important Notes**:
- **Irreversible**: Deleting volumes permanently deletes data
- **Timeout**: `timeout=10` gives container 10 seconds to stop
- **Force**: `force=True` kills the container if it doesn't stop
- **Partial Failure**: If volume deletion fails, returns error but container is still removed

---

### 6. GET /agents

**HTTP Request**:
```bash
GET /agents HTTP/1.1
```

**Code Flow**:

```python
async def list_agents():
    # Simple iteration over registry
    return {
        "count": len(agents),
        "agents": [
            {
                "id": agent["id"],
                "name": agent["name"],
                "status": agent["status"],
                "created_at": agent["created_at"],
                "task_count": len(agent["tasks"]),
            }
            for agent in agents.values()
        ]
    }
```

**Response Example**:
```json
{
  "count": 3,
  "agents": [
    {
      "id": "550e8400-...",
      "name": "data-extractor",
      "status": "ready",
      "created_at": "2026-04-28T12:34:56Z",
      "task_count": 5
    },
    {
      "id": "660e8400-...",
      "name": "web-crawler",
      "status": "ready",
      "created_at": "2026-04-28T12:35:00Z",
      "task_count": 2
    }
  ]
}
```

---

### 7. GET /health

**HTTP Request**:
```bash
GET /health HTTP/1.1
```

**Code Flow**:

```python
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "docker_available": docker_client is not None,
        "timestamp": datetime.now().isoformat(),
    }
```

**Response**:
```json
{
  "status": "healthy",
  "docker_available": true,
  "timestamp": "2026-04-28T12:00:00Z"
}
```

**Use Case**: Load balancers, monitoring systems, readiness probes

---

## Docker API Integration

### Docker Client Setup

```python
import docker

try:
    docker_client = docker.from_env()
    docker_client.ping()  # Test connection
    logger.info("docker_connected")
except Exception as e:
    logger.error("docker_connection_failed", error=str(e))
    docker_client = None
```

### Common Docker Operations

**Create Volume**:
```python
volume = docker_client.volumes.create(
    name=f"agent-{agent_id}-ws",
    driver="local"  # Default filesystem driver
)
# volume.name -> "agent-550e8400-ws"
```

**Start Container**:
```python
container = docker_client.containers.run(
    "claude-agent:latest",
    detach=True,  # Return immediately
    name="agent-550e8400-e29b",
    environment={"AGENT_ID": "..."},
    volumes={"agent-550e8400-ws": {"bind": "/workspace"}},
    mem_limit="2g",
    cpus=1.0,
)
# container.id -> full 64-char SHA
# container.short_id -> first 12 chars
```

**Execute Command in Container**:
```python
exit_code, output = container.exec_run(
    "python /app/agent_instance.py",
    stdout=True,
    stderr=True,
)
# exit_code: 0 = success, non-zero = failure
# output: bytes of stdout/stderr
```

**Get Container Stats**:
```python
stats = container.stats(stream=False)  # Single snapshot
memory_bytes = stats["memory_stats"]["usage"]
cpu_percent = stats["cpu_stats"]["cpu_usage"]["total_usage"]
```

**Stop Container**:
```python
container.stop(timeout=10)  # Wait up to 10 seconds
container.remove(force=True)  # Remove after stopping
```

**Stream Logs**:
```python
logs = container.logs(stream=True, follow=True)
for line in logs:
    print(line.decode())  # Convert bytes to string
```

---

## Error Handling Patterns

### HTTP Error Responses

```python
from fastapi import HTTPException

# Agent not found
raise HTTPException(
    status_code=404,
    detail="Agent 550e8400-... not found"
)

# Docker error
raise HTTPException(
    status_code=500,
    detail="Failed to create agent: Docker connection failed"
)

# Validation error (automatic from Pydantic)
# Invalid task data -> 422 Unprocessable Entity
```

### Structured Logging

All operations logged as JSON:

```python
logger.info(
    "agent_created",
    agent_id=agent_id,
    container_id=container.id[:12],
    duration_ms=elapsed_ms
)

# Output:
# {"event": "agent_created", "agent_id": "550e8400-...", "container_id": "a3f5c2e9d1a4", "duration_ms": 2450}
```

### Graceful Degradation

```python
try:
    stats = container.stats(stream=False)
except Exception as e:
    logger.error("status_check_failed", error=str(e))
    # Return partial status instead of 500 error
    return {
        "agent_id": agent_id,
        "error": str(e),
        "tasks": agent.get("tasks", []),  # Still return what we know
    }
```

---

## Extending the Orchestrator

### Adding a New Endpoint

**Example: Get agent output**

```python
@app.get("/agents/{agent_id}/output")
async def get_agent_output(agent_id: str):
    """Get the last output from an agent's workspace."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents[agent_id]
    
    try:
        # Get output.json from container
        container = docker_client.containers.get(agent["container_id"])
        
        # Copy file from container to local
        import tarfile
        import io
        
        bits, stat = container.get_archive("/workspace/output.json")
        tar_bytes = b"".join(bits)
        
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
            f = tar.extractfile("output.json")
            output_data = json.load(f)
        
        return output_data
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not retrieve output: {str(e)}")
```

### Using Redis for Persistence

**Current** (in-memory, lost on restart):
```python
agents = {}  # In-process dict
```

**Production** (with Redis):
```python
import redis

redis_client = redis.Redis(host="localhost", port=6379, db=0)

def get_agents():
    return {
        agent_id: json.loads(data)
        for agent_id, data in redis_client.hgetall("agents").items()
    }

def save_agent(agent_id, agent_data):
    redis_client.hset("agents", agent_id, json.dumps(agent_data))

def delete_agent(agent_id):
    redis_client.hdel("agents", agent_id)
```

### Adding Authentication

```python
from fastapi.security import HTTPBearer, HTTPAuthCredential

security = HTTPBearer()

@app.post("/agents/create")
async def create_agent(request: CreateAgentRequest, credentials: HTTPAuthCredential = Depends(security)):
    # Verify API key from credentials.credentials
    if not verify_api_key(credentials.credentials):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # ... rest of create_agent
```

### Adding Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/agents/{agent_id}/task")
@limiter.limit("10/minute")  # Max 10 tasks per minute
async def submit_task(request, background_tasks):
    # ... rest of submit_task
```

---

## Debugging Guide

### Check Docker Connection

```bash
# Is Docker running?
docker ps

# Can orchestrator reach Docker?
curl http://localhost:8000/health
# Should show: "docker_available": true
```

### View Orchestrator Logs

```bash
# If running in Docker
docker-compose logs -f orchestrator

# If running locally
# (logs go to stdout)
```

### Check Agent Status

```bash
# Get agent details
curl http://localhost:8000/agents/{agent_id}/status

# Watch logs in real-time
curl -N http://localhost:8000/agents/{agent_id}/logs | head -50

# Check container directly
docker ps -a | grep agent-{short_id}
docker logs agent-{short_id}
```

### Common Issues

**"Docker connection failed"**
```python
# Check docker_client initialization
try:
    docker_client = docker.from_env()
    docker_client.ping()
except Exception as e:
    print(f"Error: {e}")
```

**Container won't stop**
```bash
# Force kill
docker kill container-id
docker rm container-id
```

**Orphaned volumes**
```bash
# List all volumes
docker volume ls

# Remove volume
docker volume rm volume-name
```

**Agent not creating**
```python
# Check DOCKER_IMAGE is valid
docker images | grep claude-agent

# Verify Dockerfile builds
docker build -t claude-agent:latest .
```

---

## Performance Tuning

### Resource Limits

Edit `orchestrator.py` line ~180:

```python
container = client.containers.run(
    DOCKER_IMAGE,
    mem_limit="4g",  # Increase from 2g
    cpus=2.0,        # Increase from 1.0
    # ...
)
```

### Task Timeout

```python
# In TaskRequest Pydantic model
timeout: int = Field(300, description="Task timeout in seconds", ge=10, le=7200)
# Increased upper limit from 3600 to 7200 (2 hours)
```

### Concurrent Agents

Current system can handle:
- **Per host**: 10-50 agents (2GB each = 20-100GB total)
- **Per second**: 100+ task submissions
- **Task queue**: Unlimited (FastAPI handles backpressure)

Bottlenecks:
- Docker daemon responsiveness
- Host memory (2GB per agent)
- Host disk I/O (logs + volumes)

---

## Browser Automation Tools

### browse_web Tool

The `browse_web` tool enables headless browser automation within agents.

**Implementation** (`tools/custom_tools.py`):
```python
async def browse_web(args: Dict[str, Any]) -> Dict[str, Any]:
    """Automate web browser tasks using headless Chromium."""
    from browser_use import Agent
    
    url = args.get("url", "")
    task = args.get("task", "")
    
    agent = Agent(timeout=timeout)
    result = await agent.run(task, url=url)
    
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(output)
        }]
    }
```

**Container Requirements** (in Dockerfile):
```dockerfile
# Install Playwright and Chromium
RUN playwright install chromium

# Set headless mode
ENV BROWSERLESS_HEADLESS=true
```

**How It Works**:
1. Claude decides to use `browse_web()` tool
2. Agent calls tool with URL and task
3. Tool launches headless Chromium in container
4. Browser navigates, executes JavaScript, waits for content
5. Tool extracts: text, links, screenshots
6. Returns results to Claude
7. Claude analyzes and generates response/code

**Browser Capabilities**:
- Navigate websites
- Click buttons, fill forms
- Wait for dynamic content (JavaScript)
- Take screenshots (PNG)
- Extract page text/DOM
- Generate Selenium/BeautifulSoup code

**Headless Mode Benefits**:
- ✅ Works in Docker (no display server)
- ✅ Lower memory (200MB per browser)
- ✅ Faster execution
- ✅ Perfect for parallel tasks

### Tool Integration Examples

**Browser + Code Generation**:
```
Task: "Visit site and generate scraping code"
    ↓
Claude uses browse_web() to visit site
    ↓
Claude sees page structure
    ↓
Claude generates BeautifulSoup code
    ↓
Returns: code + extracted data
```

**Browser + Data Extraction**:
```
Task: "Extract all product names from site"
    ↓
Claude uses browse_web() with extract_text=true
    ↓
Tool launches browser, navigates, captures text
    ↓
Claude analyzes text, extracts products
    ↓
Returns: structured data (JSON)
```

**Multi-Tool Workflows**:
```
Task: "Visit site, scrape data, save to database"
    ↓
Claude uses browse_web() → gets data
    ↓
Claude uses query_database() → saves to DB
    ↓
Claude uses call_external_api() → notifies service
    ↓
Returns: completion status
```

### Memory & Resource Considerations

Browser automation uses more resources:
- **Memory**: Each browser ~200-300MB (vs ~100MB for non-browser tasks)
- **CPU**: High during JavaScript execution
- **Timeout**: Set appropriately (30-120 seconds recommended)

Adjust container limits if running browser-heavy workloads:
```python
# orchestrator.py line ~180
container = client.containers.run(
    DOCKER_IMAGE,
    mem_limit="4g",  # Increased for browser
    cpus=2.0,        # More CPU cores for rendering
    # ...
)
```

---

## Production Checklist

- [ ] Use Redis instead of in-memory registry
- [ ] Add authentication (API keys)
- [ ] Enable HTTPS/TLS
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Add logging aggregation (ELK, Datadog)
- [ ] Configure backups for volumes
- [ ] Implement rate limiting
- [ ] Use Kubernetes (instead of Docker Compose)
- [ ] Add health checks to load balancer
- [ ] Set resource quotas
- [ ] Enable API request logging
- [ ] Set up error alerting

---

**Last Updated**: 2026-04-28  
**Status**: Production Ready
