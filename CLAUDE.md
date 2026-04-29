# Claude Project Instructions

This is a Claude Agent SDK + Skills + browser-use architecture for autonomous AI agents.

## Project Overview

**What this is**: A Python framework combining:
- **Claude Agent SDK**: Official Anthropic agent framework
- **Skills**: Filesystem-based domain expertise in `.claude/skills/`
- **browser-use**: Python library for LLM-driven browser automation

**Why**: This is the recommended Anthropic approach (2025+) for building managed AI agents.

## Key Architecture Decisions

### 1. Official Anthropic Tools Only
- ✅ Use `anthropic` SDK (Python, native)
- ✅ Skills from `.claude/skills/` (filesystem-based)
- ✅ browser-use for web automation (4x more efficient than Playwright MCP)
- ❌ NO langchain, NO custom agent loops, NO deprecated approaches

### 2. Skills Pattern
Skills are markdown files in `.claude/skills/{skill-name}/SKILL.md` with:
```yaml
---
name: skill-name
description: What this skill does
---

# Skill Documentation
[Instructions, examples, reference material]
```

Skills provide domain expertise and are automatically discovered.

### 3. Token Efficiency
- Skills metadata always loaded (~100 tokens)
- Instructions loaded on-demand
- No penalty for unused skills
- Progressive disclosure pattern (metadata → instructions → resources)

## File Structure

```
.claude/
  ├── skills/                    # Agent Skills (auto-discovered)
  │   ├── data-extraction/
  │   │   └── SKILL.md
  │   ├── web-research/
  │   │   └── SKILL.md
  │   └── competitor-analysis/
  │       └── SKILL.md
  └── rules/                     # Optional: Path-scoped rules
      └── RULES.md

.gitignore                        # Ignore sensitive files
agent.py                          # Core agent (uses Anthropic SDK)
main.py                           # FastAPI HTTP wrapper
demo.py                           # CLI demos
requirements.txt
```

## How It Works

### Task Execution Flow

1. **User provides task** → `run_task()` function
2. **Skills auto-discovery** → Load all `.claude/skills/*/SKILL.md`
3. **Claude processes** → Makes decisions using built-in tools
4. **Tools execute** → Read, Bash, WebSearch, WebFetch, etc.
5. **Return result** → Success/error with output

### Key Functions

```python
# Run a standard task
await run_task(
    task="Research AI trends and extract insights",
    use_browser_automation=False
)

# Run a browser-based task
await run_task_with_browser(
    task="Extract pricing from acme.com",
    instructions="Optional custom guidance"
)
```

## Built-in Tools Available

- **File Operations**: Read, Write, Edit, Glob, Grep
- **Command Execution**: Bash (with timeout)
- **Web Tools**: WebSearch, WebFetch
- **Monitoring**: Monitor (for background processes)
- **Browser Automation**: bash → browser-use scripts

## Development Guidelines

### When to Create a New Skill

Create a skill when:
- ✅ You have a repeatable methodology (research, analysis, extraction)
- ✅ It's useful across multiple tasks
- ✅ It benefits from examples or reference material
- ❌ NOT for one-off tasks

Example:
```bash
mkdir -p .claude/skills/my-skill
cat > .claude/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Analyze market trends
---

# Market Analysis

## When to use
When analyzing trends in specific markets.

## Approach
1. Search for recent reports
2. Identify 3+ sources
3. Extract key metrics
4. Compare findings

## Key metrics
- Growth rate
- Market size
- Key players
EOF
```

### Testing Locally

```bash
# Check available skills
python -c "from agent import get_available_skills; print(get_available_skills())"

# Run demo
python demo.py research
python demo.py extract
python demo.py analyze
python demo.py custom "Your task here"

# Test API
python -m uvicorn main:app --reload
curl http://localhost:8000/skills
```

### Common Issues & Solutions

**Issue**: "ANTHROPIC_API_KEY not set"
```bash
export ANTHROPIC_API_KEY=sk-...
# Or create .env file: ANTHROPIC_API_KEY=sk-...
```

**Issue**: Skills not showing in /skills endpoint
```bash
# Verify structure:
ls -la .claude/skills/*/SKILL.md

# Skills must have SKILL.md with name + description in frontmatter
```

**Issue**: Task fails with timeout
- Increase timeout in `agent.py` (currently 300s)
- Use `/task/async` endpoint for long tasks
- Break complex tasks into smaller steps

## Integration Points

### FastAPI Server
```bash
# Start server
python -m uvicorn main:app --reload

# Endpoints
GET    /health              # Liveness
GET    /skills              # List skills
GET    /info                # Configuration
POST   /task                # Run synchronously
POST   /task/async          # Run asynchronously
GET    /task/{job_id}       # Check async status
```

### Docker
```bash
# Build and run
docker-compose up

# Server available at http://localhost:8001
```

## Performance Notes

- **First task**: ~10-30s (depends on network/Claude)
- **Typical task**: 15-60s
- **Complex research**: 2-5 minutes
- **Async tasks**: Use `/task/async` for UX

## Security Considerations

- ✅ API key in `.env` (included in `.gitignore`)
- ✅ Bash commands executed with timeout
- ✅ No sensitive data in URLs or logs
- ✅ Skills verified before execution

**Never**:
- ❌ Commit `.env` file
- ❌ Log API keys
- ❌ Pass sensitive data in task descriptions
- ❌ Execute untrusted code

## Version & Dependencies

- Python: 3.11+ (required by browser-use)
- Anthropic SDK: >=0.40.0
- browser-use: >=0.1.48
- FastAPI: >=0.115.0

## Useful Resources

- [Anthropic Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)
- [Agent Skills Guide](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [browser-use on GitHub](https://github.com/browser-use/browser-use)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## Common Tasks

### Research with Citations
```python
await run_task(
    "Research browser automation tools. Cite at least 3 sources. "
    "Compare Playwright vs browser-use."
)
```

### Extract Structured Data
```python
await run_task_with_browser(
    "Visit https://example.com/pricing. Extract: tiers, prices, features."
)
```

### Analyze Competitors
```python
await run_task(
    "Compare Slack vs Teams. List features, pricing, and key differences."
)
```

## Memory & Context

This file (CLAUDE.md) serves as persistent project context loaded at the start of each session. It should:
- ✅ Document architecture decisions
- ✅ Explain how to use the system
- ✅ Provide development guidelines
- ✅ Include troubleshooting help
- ❌ NOT duplicate ARCHITECTURE.md (reference it instead)

For session-specific memory, Claude can write updates to this file or create a `.claude/memory/` directory if needed.

---

**Last Updated**: 2026-04-28
**Status**: Active (Agent SDK properly integrated)
