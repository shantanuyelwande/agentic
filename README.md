# Agentic: Claude-Powered Autonomous Agents

> **Meet your autonomous workforce**: Claude-powered agents that think, decide, and act—all running securely in isolated containers on *your* infrastructure.

Self-hosted Claude-powered agents with **container isolation**, **custom tools**, and **scalable architecture**.

Think of it as **Claude Managed Agents + Daytona**, but running on your infrastructure with full control over tools, models, and execution.

## 🎯 What This Does

- **Isolated Containers**: Each agent runs in its own Docker container for security and isolation
- **Claude as Brain**: Uses Anthropic's Claude API for intelligent decision-making
- **Custom Tools**: Define domain-specific tools (data extraction, API calls, database queries, etc.)
- **HTTP API**: REST API for agent lifecycle management and task execution
- **State Persistence**: Session memory across restarts
- **Real-time Monitoring**: Stream logs, check status, monitor execution
- **Scalable**: Create and manage many agents in parallel

## 🏗️ Architecture

```
┌─────────────────┐
│  User/API Call  │
└────────┬────────┘
         │ HTTP REST API
         ▼
┌──────────────────────────┐
│  Orchestrator (FastAPI)  │
│  • Agent lifecycle       │
│  • Task scheduling       │
│  • Docker management     │
└────┬────────────────────┘
     │ Docker API
     ▼
┌────────────────────────────────┐
│  Agent Container (Isolated)     │
│  ┌──────────────────────────┐  │
│  │ Claude API (Brain)       │  │
│  │ • Decides what to do     │  │
│  │ • Calls tools            │  │
│  └────────┬─────────────────┘  │
│           │                     │
│  ┌────────▼──────────────────┐  │
│  │ Tool Execution            │  │
│  │ • extract_structured_data │  │
│  │ • query_database          │  │
│  │ • call_external_api       │  │
│  └──────────────────────────┘  │
│                                 │
│  ┌──────────────────────────┐  │
│  │ /workspace (task I/O)    │  │
│  │ /memory (state)          │  │
│  │ (isolated volumes)       │  │
│  └──────────────────────────┘  │
│                                 │
│  Memory: 2GB | CPU: 1 core      │
└────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Anthropic API key: https://console.anthropic.com

### 1. Clone & Setup

```bash
# Clone the repository
git clone <repository-url>
cd claude-managed-agents

# Create .env file with your API key
echo "ANTHROPIC_API_KEY=sk-..." > .env

# Install dependencies
pip install -r requirements.txt
```

### 2. Build Docker Image

```bash
# Build the agent container
docker build -t claude-agent:latest .

# Build the orchestrator container
docker build -f Dockerfile.orchestrator -t claude-agent-orchestrator:latest .
```

### 3. Start Services

```bash
# Start orchestrator and Redis using Docker Compose
docker-compose up -d

# Verify services are running
curl http://localhost:8000/health
```

### 4. Test with Client

```bash
# Run the test client
python client.py

# Output should show:
# ✅ Orchestrator is healthy
# ✅ Created agent
# ✅ Submitted task
# ✅ Task completed
# ✅ Retrieved output
```

## 🔄 Agent Lifecycle

Understanding how agents work end-to-end:

### 1️⃣ **Create Agent** (Setup Phase)

When you create an agent, the orchestrator:
- Generates a unique ID
- Creates isolated Docker volumes (workspace + memory)
- Starts a container with resource limits (2GB RAM, 1 CPU)
- Returns the agent_id for future references

```bash
curl -X POST http://localhost:8000/agents/create \
  -H "Content-Type: application/json" \
  -d '{"name": "data-extractor"}'

# Returns: {"agent_id": "550e8400-...", "status": "created"}
```

**What happens inside the container:**
- Container pulls the `claude-agent:latest` image
- Mounts `/workspace` (for task input/output)
- Mounts `/memory` (for session state)
- Waits for tasks to arrive

---

### 2️⃣ **Submit Task** (Execution Phase)

Submit a task for the agent to process:

```bash
curl -X POST http://localhost:8000/agents/550e8400-{id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Extract emails from: john@example.com, 555-123-4567",
    "timeout": 300
  }'

# Returns: {"task_id": "8f3a1f4e-...", "status": "submitted"}
```

**What happens (asynchronously):**
1. Orchestrator writes task.json to container's `/workspace`
2. Returns immediately to client (non-blocking)
3. Background process starts: `python agent_instance.py`
4. Agent reads `/workspace/task.json`
5. Agent initializes Claude API client
6. Agent implements agentic loop:
   - Calls Claude with task + available tools
   - Claude decides which tool(s) to use
   - Agent executes tools (extract_structured_data, etc.)
   - Loop continues until Claude says "I'm done"
7. Agent writes results to `/workspace/output.json`
8. Agent saves session state to `/memory/session.json`
9. Task status changes to "completed"

---

### 3️⃣ **Monitor Progress** (Polling Phase)

Check if task is done:

```bash
# Poll for status (call repeatedly every second)
curl http://localhost:8000/agents/550e8400-{id}/status

# Response shows task status:
# "tasks": [
#   {
#     "task_id": "8f3a1f4e-...",
#     "status": "completed",  # submitted → running → completed
#     "created_at": "2026-04-28T...",
#     "completed_at": "2026-04-28T..."
#   }
# ]
```

**Client pattern (from client.py)**:
```python
for i in range(max_wait):
    status = await client.get(f"/agents/{agent_id}/status")
    tasks = status.json()["tasks"]
    
    for task in tasks:
        if task["task_id"] == task_id:
            if task["status"] == "completed":
                print("✅ Task completed!")
                break
            elif task["status"] == "failed":
                print("❌ Task failed")
                break
    
    await asyncio.sleep(1)  # Poll every second
```

---

### 4️⃣ **Stream Logs** (Real-time Monitoring)

Watch the agent work in real-time:

```bash
# Stream logs (connection stays open)
curl -N http://localhost:8000/agents/550e8400-{id}/logs

# Output (Server-Sent Events):
# data: [2026-04-28T12:35:00] Agent starting
# data: [2026-04-28T12:35:01] Task received: extract emails
# data: [2026-04-28T12:35:02] Initializing Claude API
# data: [2026-04-28T12:35:03] Calling Claude
# data: [2026-04-28T12:35:05] Tool: extract_structured_data
# data: [2026-04-28T12:35:06] Result: found 3 emails
# data: [2026-04-28T12:35:07] Agent completed
```

---

### 5️⃣ **Cleanup** (Termination Phase)

Delete the agent and free resources:

```bash
curl -X DELETE http://localhost:8000/agents/550e8400-{id}

# Returns: {"status": "terminated", "agent_id": "550e8400-..."}
```

**What happens:**
- Container is stopped (SIGTERM, then SIGKILL if needed)
- Container is removed from Docker
- Workspace volume is deleted (task.json, output.json)
- Memory volume is deleted (session.json)
- Resources are freed

---

## 📚 API Usage Guide

### 1. Health Check

**When**: Before creating agents, to verify orchestrator is running

```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "docker_available": true,
  "timestamp": "2026-04-28T12:00:00Z"
}
```

---

### 2. Create Agent

**When**: Starting a new agent instance

```bash
curl -X POST http://localhost:8000/agents/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "data-extractor"
  }'
```

**Response**:
```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "data-extractor",
  "status": "created",
  "container_id": "a3f5c2e9d1a4",
  "created_at": "2026-04-28T12:00:00Z"
}
```

**Notes**:
- Agent starts in background immediately
- Use returned `agent_id` for all subsequent operations
- Name is optional (defaults to `agent-{short_id}`)

---

### 3. Submit Task

**When**: You want an agent to process something

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Extract emails and phone numbers from this text: john@example.com, 555-123-4567",
    "timeout": 300
  }'
```

**Response** (returns immediately):
```json
{
  "task_id": "8f3a1f4e-2a1b-4c3d-8e5f-9g0h1i2j3k4l",
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "submitted",
  "created_at": "2026-04-28T12:00:05Z"
}
```

**Parameters**:
- `task` (required): What you want Claude to do
- `timeout` (optional): Max seconds to wait (10-3600, default 300)

**Important**: Response comes back immediately even though task is still running!

---

### 4. Check Status

**When**: Poll to see if task is done (call repeatedly)

```bash
curl http://localhost:8000/agents/{agent_id}/status
```

**Response**:
```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "data-extractor",
  "status": "ready",
  "container_status": "running",
  "created_at": "2026-04-28T12:00:00Z",
  "memory_usage_mb": 512.5,
  "tasks": [
    {
      "task_id": "8f3a1f4e-...",
      "status": "completed",
      "created_at": "2026-04-28T12:00:05Z",
      "completed_at": "2026-04-28T12:00:25Z"
    }
  ]
}
```

**Task Status Values**:
- `submitted`: Task queued, waiting to start
- `running`: Agent is processing (might be fast)
- `completed`: Task finished successfully
- `failed`: Task encountered an error

**Polling Pattern**:
```bash
# Check every 1 second until task completes
for i in {1..300}; do
  status=$(curl -s http://localhost:8000/agents/{agent_id}/status)
  task_status=$(echo $status | jq '.tasks[0].status')
  
  if [ "$task_status" = '"completed"' ]; then
    echo "✅ Task done!"
    break
  elif [ "$task_status" = '"failed"' ]; then
    echo "❌ Task failed"
    break
  fi
  
  sleep 1
done
```

---

### 5. Stream Logs (Real-time)

**When**: You want to watch the agent work live

```bash
curl -N http://localhost:8000/agents/{agent_id}/logs
```

**Output** (Server-Sent Events):
```
data: [2026-04-28T12:00:05] Agent starting with ID: 550e8400-...
data: [2026-04-28T12:00:06] Task received: extract emails and phone...
data: [2026-04-28T12:00:06] Initializing Claude API
data: [2026-04-28T12:00:07] Calling Claude API
data: [2026-04-28T12:00:09] Tool use requested: extract_structured_data
data: [2026-04-28T12:00:09] Executing tool: extract_structured_data
data: [2026-04-28T12:00:09] Tool result: {'emails': ['john@example.com'], 'phones': ['555-123-4567']}
data: [2026-04-28T12:00:10] Agent finished
```

**Notes**:
- Connection stays open (streaming)
- Works even if container has exited (gets history)
- Use `-N` flag with curl to disable buffering
- In Python: `response.iter_lines()` or `iter_content()`

**Python Example**:
```python
import requests

response = requests.get(
    f"http://localhost:8000/agents/{agent_id}/logs",
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b"data: "):
        print(line[6:].decode())
```

---

### 6. List All Agents

**When**: You want to see what agents are running

```bash
curl http://localhost:8000/agents
```

**Response**:
```json
{
  "count": 3,
  "agents": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "data-extractor",
      "status": "ready",
      "created_at": "2026-04-28T12:00:00Z",
      "task_count": 5
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "web-crawler",
      "status": "ready",
      "created_at": "2026-04-28T12:01:00Z",
      "task_count": 2
    }
  ]
}
```

---

### 7. Terminate Agent

**When**: You're done with an agent (frees resources)

```bash
curl -X DELETE http://localhost:8000/agents/{agent_id}
```

**Response**:
```json
{
  "status": "terminated",
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "terminated_at": "2026-04-28T12:00:30Z"
}
```

**What Gets Deleted**:
- Container (stopped and removed)
- Workspace volume (task.json, output.json)
- Memory volume (session.json)
- Agent registry entry

**⚠️ Warning**: This is irreversible! Data is deleted permanently.

## 📤 Getting Task Results

After a task completes, you can retrieve its output. The agent saves results to `/workspace/output.json` in the container.

### Via Docker

```bash
# Connect to container and view output
docker exec $(docker ps -q -f "name=agent-550e8400") \
  cat /workspace/output.json | jq .
```

### Example Output

```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_id": "8f3a1f4e-2a1b-4c3d-8e5f-9g0h1i2j3k4l",
  "task": "Extract emails from: john@example.com, 555-123-4567",
  "status": "completed",
  "started_at": "2026-04-28T12:00:06Z",
  "finished_at": "2026-04-28T12:00:15Z",
  "final_output": "I found 1 email address: john@example.com",
  "tool_calls": [
    {
      "name": "extract_structured_data",
      "input": {
        "text": "john@example.com, 555-123-4567"
      },
      "id": "toolu_01234567890123456789"
    }
  ],
  "messages": [
    {
      "type": "assistant",
      "content": "I'll extract the email and phone number from the provided text."
    },
    {
      "type": "assistant",
      "content": "I found 1 email address: john@example.com and 1 phone number: 555-123-4567"
    }
  ],
  "error": null
}
```

**Output Fields**:
- `final_output`: Claude's final response (what to show the user)
- `tool_calls`: List of tools Claude used and their inputs
- `messages`: Full conversation history
- `status`: "completed" or "failed"
- `error`: Error message if task failed

### Via API (Recommended for AI Agents)

**Stream live execution logs** while task is running:
```bash
curl -N http://localhost:8000/agents/{agent_id}/logs
```

**Get task status and metadata** (check if done):
```bash
curl http://localhost:8000/agents/{agent_id}/status
```

Returns task status, timestamps, and execution info:
```json
{
  "agent_id": "550e8400-...",
  "tasks": [
    {
      "task_id": "8f3a1f4e-...",
      "status": "completed",
      "created_at": "2026-04-28T12:00:05Z",
      "completed_at": "2026-04-28T12:00:15Z"
    }
  ]
}
```

## 📋 Complete AI Agent Workflow

For autonomous AI agents to use Agentic without human intervention:

```python
import requests
import time
import json

BASE_URL = "http://localhost:8000"

# 1. Create agent
agent = requests.post(f"{BASE_URL}/agents/create", json={"name": "auto-agent"}).json()
agent_id = agent["agent_id"]

# 2. Submit task
task = requests.post(f"{BASE_URL}/agents/{agent_id}/task", json={
    "task": "Extract all emails from: john@example.com, jane@test.org",
    "timeout": 60
}).json()
task_id = task["task_id"]

# 3. Poll for completion
max_wait = 60
for i in range(max_wait):
    status = requests.get(f"{BASE_URL}/agents/{agent_id}/status").json()
    task_status = status["tasks"][0]["status"]
    
    if task_status == "completed":
        print("✅ Task completed!")
        # Get full output
        output = requests.get(f"{BASE_URL}/agents/{agent_id}/logs").text
        print(output)
        break
    elif task_status == "failed":
        print("❌ Task failed")
        break
    
    time.sleep(1)

# 4. Parse results from logs or status
# Look for "final_output" field in logs for Claude's response
# Look for "tool_calls" for tools used
# Look for "error" field if task failed

# 5. Cleanup
requests.delete(f"{BASE_URL}/agents/{agent_id}")
```

---

## 🔍 Understanding Agent Execution Logs

When you stream logs via `/agents/{agent_id}/logs`, you'll see JSON events like:

```json
{"event": "agent_starting", "agent_id": "550e8400-...", "timestamp": "2026-04-28T12:00:05Z"}
{"event": "task_received", "task": "Extract emails..."}
{"event": "claude_calling", "model": "claude-sonnet-4-6"}
{"event": "tool_use", "tool_name": "extract_structured_data", "input": {"text": "..."}}
{"event": "tool_result", "result": "Found 2 emails"}
{"event": "agent_completed", "status": "completed", "final_output": "I found..."}
```

**Key events to look for**:
- `agent_starting`: Agent initialized
- `task_received`: Task loaded from workspace
- `claude_calling`: API call to Claude
- `tool_use`: Claude requested a tool
- `tool_result`: Tool execution result
- `agent_completed` or `agent_failed`: Final status
- `error`: Any errors during execution

**Parsing logs in code**:
```python
import json

# Parse streaming JSON logs
for line in response.iter_lines():
    if line.startswith(b"data: "):
        event = json.loads(line[6:])
        if event.get("event") == "agent_completed":
            print(event.get("final_output"))
        elif event.get("event") == "error":
            print(f"Error: {event.get('error')}")
```

---

## 🌐 Built-in Tools

Your agents come with powerful tools Claude can use:

### 1. **extract_structured_data**
Extract emails, phone numbers, and URLs from text
```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{"task":"Extract emails from: john@example.com, jane@test.org"}'
```

### 2. **query_database**
Execute safe SQL queries with injection prevention
```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{"task":"Query database: SELECT * FROM users WHERE active=1 LIMIT 10"}'
```

### 3. **call_external_api**
Call REST APIs on whitelisted domains
```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{"task":"Get data from: https://jsonplaceholder.typicode.com/users/1"}'
```

### 4. **browse_web** (NEW! 🎉)
Automate web browser tasks using headless Chromium
```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{"task":"Visit https://example.com and extract all product names and prices"}'
```

---

## 🌐 Browser Automation Examples

### Visit a Website and Extract Data

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com/products and extract product names, prices, and availability. Return as JSON."
  }'
```

**Claude will**:
1. Open browser (headless, no GUI)
2. Navigate to the website
3. Wait for JavaScript to load
4. Extract structured data
5. Generate extraction code (BeautifulSoup, regex, etc.)
6. Return both the code and results

---

### Generate Web Scraping Code

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com and generate Python code using BeautifulSoup to scrape all article titles and links. Return the code with comments."
  }'
```

**Response includes**:
```python
from bs4 import BeautifulSoup
import requests

response = requests.get('https://example.com')
soup = BeautifulSoup(response.content, 'html.parser')

articles = []
for item in soup.find_all('article'):
    title = item.find('h2').text
    link = item.find('a')['href']
    articles.append({'title': title, 'link': link})

return articles
```

---

### Automate Form Filling

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com/search, fill the search box with \"python\", and extract the top 5 results. Also generate Selenium code to automate this process."
  }'
```

---

### Take Screenshots and Extract Text

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://news.ycombinator.com, take a screenshot, and extract the top 10 story headlines with their upvote counts"
  }'
```

---

### Generate Code to Automate Complex Tasks

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com and generate Selenium code to: 1. Click the Login button 2. Fill email field with test@example.com 3. Fill password field 4. Click Sign In 5. Wait for dashboard to load"
  }'
```

**Returns Selenium code**:
```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

driver = webdriver.Chrome()
driver.get('https://example.com')

# Click login button
login_btn = driver.find_element(By.CSS_SELECTOR, 'button.login')
login_btn.click()

# Fill email
email = driver.find_element(By.ID, 'email')
email.send_keys('test@example.com')

# ... rest of automation
```

---

## 🛠️ Creating Custom Tools

Define tools in `tools/custom_tools.py`. Example:

```python
def my_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Tool description."""
    param = args.get("param", "")
    
    if not param:
        return {
            "content": [{"type": "text", "text": "Error: param required"}],
            "is_error": True
        }
    
    result = process(param)
    return {
        "content": [{"type": "text", "text": json.dumps(result)}]
    }
```

Register in `tools/__init__.py` and Claude will discover it automatically!

## 🔧 Configuration

### Environment Variables

```bash
ANTHROPIC_API_KEY=sk-...              # Required: Your API key
DOCKER_IMAGE=claude-agent:latest      # Optional
PORT=8000                             # Optional: API port
BROWSERLESS_HEADLESS=true             # Headless browser mode (default)
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH   # Custom Chromium location
```

### Customize Resources

Edit `docker-compose.yml` or `orchestrator.py`:
- Agent memory limit: Change `mem_limit: 2g` (increase for browser tasks)
- CPU limit: Change `cpus: 1.0`
- Task timeout: Pass in task request (useful for long browser sessions)
- Browser timeout: Browser-use respects task timeout parameter

### Browser-Specific Configuration

Browser runs **headless** (no GUI) inside each container:

```dockerfile
# Dockerfile already configured for headless browsing
ENV BROWSERLESS_HEADLESS=true
RUN playwright install chromium
```

**Headless Benefits**:
- ✅ Works in Docker containers (no display server needed)
- ✅ Lower memory usage than GUI browsers
- ✅ Faster page rendering
- ✅ Perfect for automation
- ✅ Parallel browser instances per agent

**Still Supports**:
- Screenshot capture (PNG)
- Text extraction from rendered pages
- JavaScript execution
- Form filling and interaction
- Dynamic content loading

## 📊 Project Structure

```
.
├── agent_instance.py              # Agent inside container
├── orchestrator.py                # API server
├── tools/
│   ├── __init__.py
│   └── custom_tools.py            # Your tools
├── Dockerfile                     # Agent image
├── Dockerfile.orchestrator        # Orchestrator image
├── docker-compose.yml             # Multi-container setup
├── requirements.txt               # Dependencies
├── client.py                      # Test client
├── .env                          # API key (excluded)
├── .gitignore
├── README.md                     # This file
└── LICENSE
```

## 🔐 Security

- Input validation on all tools
- Container isolation per agent
- Resource limits (memory, CPU)
- Whitelist allowed domains
- No secrets in logs
- Dangerous SQL/shell ops blocked

## 🚀 Running Multiple Agents in Parallel

Each agent runs independently in its own container. You can create many agents and submit tasks to them in parallel.

### Create Multiple Agents

```bash
for i in {1..5}; do
  AGENT=$(curl -s -X POST http://localhost:8000/agents/create \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"agent-$i\"}")
  
  AGENT_ID=$(echo $AGENT | jq -r '.agent_id')
  echo "Created agent $i: $AGENT_ID"
done
```

### Submit Tasks to Multiple Agents

```bash
# Create agents
AGENT1=$(curl -s -X POST http://localhost:8000/agents/create -d '{"name":"extractor-1"}' | jq -r '.agent_id')
AGENT2=$(curl -s -X POST http://localhost:8000/agents/create -d '{"name":"extractor-2"}' | jq -r '.agent_id')

# Submit tasks simultaneously
curl -X POST http://localhost:8000/agents/$AGENT1/task \
  -d '{"task":"Extract emails from: john@example.com"}' &

curl -X POST http://localhost:8000/agents/$AGENT2/task \
  -d '{"task":"Extract phone numbers from: 555-123-4567"}' &

wait  # Wait for both submissions
```

**Advantages**:
- Parallel execution: Tasks run simultaneously
- Isolation: Agents don't interfere with each other
- Scalability: Add more agents as needed
- Resilience: One agent failing doesn't affect others

**Limits per Host**:
- Memory: ~10-50 agents (2GB each)
- CPU: Limited by your system
- Disk: Storage for volumes

---

## 📈 Production Scaling

For production deployments:

**Option 1: Docker Swarm**
```bash
docker service create --replicas 3 -p 8000:8000 \
  --name orchestrator \
  -e ANTHROPIC_API_KEY=$API_KEY \
  claude-agent-orchestrator:latest
```

**Option 2: Kubernetes**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orchestrator
  template:
    metadata:
      labels:
        app: orchestrator
    spec:
      containers:
      - name: orchestrator
        image: claude-agent-orchestrator:latest
        ports:
        - containerPort: 8000
```

**Additional Services Needed**:
- Redis: Replace in-memory agent registry
- PostgreSQL: Store agent history and results
- Monitoring: Prometheus + Grafana
- Logging: ELK Stack or Datadog
- Load Balancer: Distribute requests

See [ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md) for production migration steps.

## 🐛 Troubleshooting

### Orchestrator Not Responding

**Symptom**: `curl: (7) Failed to connect to localhost port 8000`

**Solutions**:
```bash
# 1. Check Docker is running
docker ps

# 2. Check orchestrator container is running
docker-compose ps

# 3. View orchestrator logs
docker-compose logs orchestrator

# 4. Restart services
docker-compose down
docker-compose up -d
sleep 5
curl http://localhost:8000/health
```

---

### Agent Creation Fails

**Symptom**: `Error: Failed to create agent: Docker connection failed`

**Solutions**:
```bash
# 1. Verify Docker image exists
docker images | grep claude-agent

# 2. Rebuild the image if missing
docker build -t claude-agent:latest .

# 3. Check Docker daemon permissions
docker ps  # Should not show permission denied

# 4. Check volume creation
docker volume ls | grep agent
```

---

### Task Not Starting/Running

**Symptom**: Task stays in "submitted" status, never starts

**Solutions**:
```bash
# 1. Check container is actually running
docker ps | grep agent-{short_id}

# 2. View container logs
docker logs agent-{short_id}

# 3. Check if task.json was written
docker exec agent-{short_id} ls -la /workspace

# 4. Check API key is set
docker-compose config | grep ANTHROPIC_API_KEY
```

---

### Task Fails with Error

**Symptom**: Task status shows "failed"

**Solutions**:
```bash
# 1. Stream logs to see the error
curl -N http://localhost:8000/agents/{agent_id}/logs | tail -20

# 2. Get full status
curl http://localhost:8000/agents/{agent_id}/status | jq '.tasks[0]'

# 3. Check container exit code
docker inspect agent-{short_id} | jq '.[0].State.ExitCode'
# 0 = success, non-zero = error
```

---

### Task Timeout

**Symptom**: Task exceeds timeout without completing

**Solutions**:
```bash
# 1. Increase timeout in task request
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{"task":"...", "timeout": 600}'  # 10 minutes instead of 5

# 2. Check what's taking long
curl -N http://localhost:8000/agents/{agent_id}/logs | grep -i "tool\|error"

# 3. Check agent resource usage
docker stats agent-{short_id}  # CPU and memory
```

---

### Memory Issues

**Symptom**: Agent container stops or OOM kills

**Solutions**:
```bash
# 1. Check current limits
docker inspect agent-{short_id} | jq '.[0].HostConfig.Memory'
# Returns bytes (divide by 1GB = 1073741824)

# 2. Increase memory limit in orchestrator.py (~line 180)
# mem_limit="4g"  # Change from 2g to 4g

# 3. Or edit docker-compose.yml:
# environment:
#   - MEM_LIMIT=4g

# 4. Rebuild and restart
docker-compose down
docker build -t claude-agent:latest .
docker-compose up -d
```

---

### High Memory Usage

**Symptom**: Agents use too much memory

**Solutions**:
```bash
# 1. Monitor memory usage
docker stats

# 2. Reduce container memory limit if possible (may cause OOM)
# mem_limit="1g"  # Reduce from 2g

# 3. Implement per-task memory cleanup
# Edit agent_instance.py to explicitly del large objects

# 4. Use multiple smaller agents instead of one large one
```

---

### Docker Daemon Issues

**Symptom**: `Cannot connect to Docker daemon`

**Solutions**:
```bash
# Mac
docker info  # Should work

# Linux (may need sudo)
sudo usermod -aG docker $USER
newgrp docker

# Docker Desktop not running
# (Restart Docker Desktop)

# Volume mount issues
docker run -it --rm -v /test:/test alpine ls /test
```

---

### API Shows Old Data

**Symptom**: Agent list shows deleted agents, or old task status

**Solutions**:
```bash
# This is because agents are stored in-memory
# Restarting clears everything:
docker-compose restart orchestrator

# For production, use Redis:
# See ORCHESTRATOR_GUIDE.md -> "Using Redis for Persistence"
```

---

### Still Having Issues?

1. **Check logs**: `docker-compose logs -f`
2. **Check status**: `curl http://localhost:8000/health | jq .`
3. **Run test client**: `python client.py` (shows full workflow)
4. **Check documentation**: [ARCHITECTURE.md](ARCHITECTURE.md), [ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md)

## 🔗 Complete Workflow Example

Here's a full end-to-end example:

```bash
#!/bin/bash

# 1. Verify orchestrator is running
curl -s http://localhost:8000/health | jq .

# 2. Create agent
AGENT=$(curl -s -X POST http://localhost:8000/agents/create \
  -H "Content-Type: application/json" \
  -d '{"name":"email-extractor"}')

AGENT_ID=$(echo $AGENT | jq -r '.agent_id')
echo "Created agent: $AGENT_ID"

# 3. Submit task
TASK=$(curl -s -X POST http://localhost:8000/agents/$AGENT_ID/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Extract all email addresses from: john@example.com, jane@test.org, support@acme.com"
  }')

TASK_ID=$(echo $TASK | jq -r '.task_id')
echo "Submitted task: $TASK_ID"

# 4. Poll for completion
echo "Waiting for task..."
for i in {1..30}; do
  STATUS=$(curl -s http://localhost:8000/agents/$AGENT_ID/status)
  TASK_STATUS=$(echo $STATUS | jq -r '.tasks[0].status')
  
  if [ "$TASK_STATUS" = "completed" ]; then
    echo "✅ Task completed!"
    echo $STATUS | jq '.tasks[0]'
    break
  elif [ "$TASK_STATUS" = "failed" ]; then
    echo "❌ Task failed"
    break
  else
    echo "  Status: $TASK_STATUS (${i}s)"
    sleep 1
  fi
done

# 5. View logs
echo ""
echo "Agent logs:"
curl -s -N http://localhost:8000/agents/$AGENT_ID/logs | head -20

# 6. Cleanup
echo ""
echo "Cleaning up..."
curl -s -X DELETE http://localhost:8000/agents/$AGENT_ID | jq .
```

**Output**:
```
Created agent: 550e8400-e29b-41d4-a716-446655440000
Submitted task: 8f3a1f4e-2a1b-4c3d-8e5f-9g0h1i2j3k4l
Waiting for task...
  Status: submitted (1s)
  Status: running (2s)
✅ Task completed!
{
  "task_id": "8f3a1f4e-2a1b-4c3d-8e5f-9g0h1i2j3k4l",
  "status": "completed",
  "created_at": "2026-04-28T12:00:05Z",
  "completed_at": "2026-04-28T12:00:15Z"
}

Agent logs:
data: [2026-04-28T12:00:05] Agent starting
data: [2026-04-28T12:00:06] Task received: Extract all email addresses
data: [2026-04-28T12:00:07] Initializing Claude API
data: [2026-04-28T12:00:08] Calling Claude API
...
```

---

## 📝 API Reference

| Method | Endpoint | Purpose | Response |
|--------|----------|---------|----------|
| GET | `/health` | Check orchestrator status | `{"status": "healthy", ...}` |
| POST | `/agents/create` | Create new agent | `{"agent_id": "...", ...}` |
| POST | `/agents/{id}/task` | Submit task (async) | `{"task_id": "...", ...}` |
| GET | `/agents/{id}/status` | Check task progress | `{"tasks": [...], ...}` |
| GET | `/agents/{id}/logs` | Stream logs (SSE) | `data: log lines` |
| DELETE | `/agents/{id}` | Terminate agent | `{"status": "terminated"}` |
| GET | `/agents` | List all agents | `{"count": N, "agents": [...]}` |

**Interactive Documentation**: Open http://localhost:8000/docs in browser for Swagger UI

## 🤝 Contributing

Contributions welcome! Ideas:
- Additional tools/skills
- WebUI dashboard
- Kubernetes operators
- More language support

## 📄 License

MIT License - See LICENSE file

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design, components, data flow, security model
- **[ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md)** - Deep dive into orchestrator internals, endpoints, debugging
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Quick setup, customization, production checklist
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contributing guidelines, code style, tool development

## 🎯 Next Steps

1. ✅ **Setup**: Run quick start above
2. ✅ **Test**: Run `python client.py` for full workflow demo
3. 📖 **Learn**: Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system
4. 🔧 **Customize**: Add custom tools to `tools/custom_tools.py`
5. 🚀 **Deploy**: Follow production checklist in [GETTING_STARTED.md](GETTING_STARTED.md)
6. 🐛 **Debug**: Use [ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md) for troubleshooting

## 💡 Common Tasks

**Extract structured data**:
```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{"task":"Extract emails, phone numbers, and URLs from: john@example.com 555-123-4567 https://example.com"}'
```

**Query database**:
```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{"task":"Query database: SELECT COUNT(*) FROM users WHERE active=1"}'
```

**Call external API**:
```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{"task":"Get data from: https://jsonplaceholder.typicode.com/users/1"}'
```

**Create multiple agents**:
```bash
for i in {1..5}; do
  curl -X POST http://localhost:8000/agents/create -d "{\"name\":\"agent-$i\"}"
done
```

---

**Built with ❤️ using Claude & Docker**

Questions? Check [ARCHITECTURE.md](ARCHITECTURE.md) or [ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md)
