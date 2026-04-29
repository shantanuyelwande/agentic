# Getting Started with Claude Managed Agents

## 📦 What You Have

A complete, production-ready implementation of Claude-powered agents running in isolated Docker containers with:

- **agent_instance.py** - Agent brain using Claude API
- **orchestrator.py** - HTTP API server managing agents
- **tools/** - Custom tool definitions
- **Dockerfiles** - Container images
- **docker-compose.yml** - Multi-container setup
- **client.py** - Test client demonstrating usage

## 🚀 5-Minute Setup

### 1. Create .env File

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-...
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Build Docker Images

```bash
# Agent container
docker build -t claude-agent:latest .

# Orchestrator container  
docker build -f Dockerfile.orchestrator -t claude-agent-orchestrator:latest .
```

### 4. Start Services

```bash
docker-compose up -d

# Wait a few seconds for startup
sleep 5

# Verify
curl http://localhost:8000/health
# Should return: {"status": "healthy", ...}
```

### 5. Test It

```bash
python client.py

# Should show:
# ✅ Orchestrator is healthy
# ✅ Created agent
# ✅ Submitted task
# ✅ Task completed
```

## 📖 Next Steps

1. **Read README.md** - Full documentation and API reference
2. **Check CONTRIBUTING.md** - How to add custom tools
3. **Explore client.py** - See usage patterns
4. **Add Tools** - Edit `tools/custom_tools.py` with your logic

## 🌐 Browser Automation Setup

Browser automation is **already included**! Each agent container has:
- ✅ Playwright (browser automation library)
- ✅ Chromium (headless browser)
- ✅ browser-use library (high-level browser agent)

### Browser Runs Headless (No GUI)

```dockerfile
# Already configured in Dockerfile:
ENV BROWSERLESS_HEADLESS=true
RUN playwright install chromium
```

Headless means:
- ✅ Runs in Docker without display server
- ✅ Lower memory usage
- ✅ Faster execution
- ✅ Perfect for automation
- ✅ Can take screenshots and extract text

### Test Browser Capability

```bash
# Create agent
AGENT=$(curl -s -X POST http://localhost:8000/agents/create \
  -d '{"name":"browser-test"}' | jq -r '.agent_id')

# Submit browser task
curl -X POST http://localhost:8000/agents/$AGENT/task \
  -d '{
    "task": "Visit https://example.com and tell me the page title",
    "timeout": 30
  }' | jq .

# Check status
curl http://localhost:8000/agents/$AGENT/status | jq '.tasks[0].status'

# View logs
curl -N http://localhost:8000/agents/$AGENT/logs | head -20

# Cleanup
curl -X DELETE http://localhost:8000/agents/$AGENT
```

---

## 🛠️ Customization

### Add a Custom Tool

Edit `tools/custom_tools.py`:

```python
def my_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """My custom tool."""
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

Then register in `tools/__init__.py`:

```python
from .custom_tools import my_tool

__all__ = ["my_tool"]
```

Claude will discover it automatically!

### Adjust Resource Limits

Edit `docker-compose.yml` under orchestrator service:

```yaml
environment:
  - DOCKER_IMAGE=claude-agent:latest
  # Change orchestrator memory
  mem_limit: 4g
  cpus: 2
```

Or in agent container instantiation (orchestrator.py line ~180):

```python
container = client.containers.run(
    DOCKER_IMAGE,
    mem_limit="4g",  # Change this
    cpus=2.0,        # Or this
    ...
)
```

## 📚 API Quick Reference

```bash
# Create agent
curl -X POST http://localhost:8000/agents/create \
  -d '{"name":"my-agent"}'

# Submit task
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{"task":"Extract emails from..."}'

# Check status
curl http://localhost:8000/agents/{id}/status

# Stream logs
curl -N http://localhost:8000/agents/{id}/logs

# List all agents
curl http://localhost:8000/agents

# Terminate
curl -X DELETE http://localhost:8000/agents/{id}
```

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Docker not found | Make sure Docker daemon is running: `docker ps` |
| API not responding | Check logs: `docker-compose logs orchestrator` |
| Task timeout | Increase timeout: `"timeout": 600` in task request |
| No agent output | Check agent logs: `curl http://localhost:8000/agents/{id}/logs` |

## 📁 Key Files Explained

| File | Purpose |
|------|---------|
| `agent_instance.py` | Runs inside container, talks to Claude |
| `orchestrator.py` | HTTP API, manages containers |
| `tools/custom_tools.py` | Your domain-specific tools |
| `Dockerfile` | Agent container image |
| `Dockerfile.orchestrator` | Orchestrator container image |
| `docker-compose.yml` | Brings it all together |
| `client.py` | Example client showing how to use API |

## 🎯 Common Tasks

### Run Multiple Agents

```bash
for i in {1..3}; do
  curl -X POST http://localhost:8000/agents/create \
    -d "{\"name\":\"agent-$i\"}"
done
```

### Extract Data from Text

```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{
    "task": "Extract emails and phone numbers from: john@example.com 555-123-4567",
    "timeout": 60
  }'
```

### Query Database

```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{
    "task": "Query the database: SELECT * FROM users WHERE active=1 LIMIT 10"
  }'
```

### Call External API

```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{
    "task": "Get data from API: GET https://jsonplaceholder.typicode.com/users"
  }'
```

### Browser Automation - Visit Website

```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{
    "task": "Visit https://example.com and extract all product names and prices"
  }'
```

### Browser Automation - Generate Code

```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{
    "task": "Visit https://example.com and generate Python BeautifulSoup code to scrape product data"
  }'
```

### Browser Automation - Form Automation

```bash
curl -X POST http://localhost:8000/agents/{id}/task \
  -d '{
    "task": "Visit https://example.com/search, fill search box with \"python\", and extract top 5 results. Generate Selenium code for automation."
  }'
```

## 🔗 Resources

- [README.md](README.md) - Full documentation
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contributing guidelines
- [CLAUDE.md](CLAUDE.md) - Project context
- [LICENSE](LICENSE) - MIT License

## ✅ Checklist for Production

- [ ] Set strong `ANTHROPIC_API_KEY`
- [ ] Increase agent memory limit if needed
- [ ] Set resource limits for Docker
- [ ] Use Redis for persistent job queue
- [ ] Add monitoring (Prometheus, Grafana)
- [ ] Add logging aggregation (ELK)
- [ ] Run behind reverse proxy (nginx)
- [ ] Enable HTTPS/TLS
- [ ] Set up automated backups
- [ ] Add authentication to API
- [ ] Rate limiting

## 🆘 Get Help

1. Check README.md FAQ section
2. Review CONTRIBUTING.md
3. Check agent logs: `docker-compose logs -f`
4. Run client.py in debug mode

## 🎉 You're Ready!

You now have a fully functional Claude-powered agent system running on your infrastructure. Start building!

---

**Questions?** Check the documentation files or reach out to the community.
