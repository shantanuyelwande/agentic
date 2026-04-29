# Skills System

Skills are data extraction tools that Claude can use during task execution.

## What Are Skills?

Skills are Python functions wrapped as LLM tools. They help Claude extract and process information from scraped web content.

## Available Skills

| Skill | Purpose | Input | Output |
|-------|---------|-------|--------|
| `tool_extract_emails` | Extract email addresses | Text | List of emails |
| `tool_extract_phone_numbers` | Extract US phone numbers | Text | List of phone numbers |
| `tool_extract_urls` | Extract URLs from text | Text | List of URLs |
| `tool_parse_pricing` | Extract pricing info | Text | Dict with tiers, prices, currency |
| `tool_extract_company_info` | Extract company details | Text | Dict with emails, phones, URLs, names |
| `tool_summarize` | Summarize text | Text + max_sentences | Concise summary |

## Two Ways to Use Skills

### 1. **Direct Usage** (Post-Processing)

Use skills as Python functions to process already-scraped content:

```python
from skills import extract_emails, extract_company_info

# After scraping content
emails = extract_emails(scraped_text)
company_info = extract_company_info(scraped_text)

print(f"Found {len(emails)} emails: {emails}")
print(f"Company URLs: {company_info['urls']}")
```

**When to use:** When you've already scraped content and want to extract structured data in Python.

### 2. **Tool Usage** (Claude Calls During Task)

Claude automatically has access to skills as tools during task execution:

```python
from agent import run_task

# Claude will use tools as needed
result = await run_task(
    task="Go to techcorp.io and extract all contact information: emails, phone numbers, and URLs"
)

# Claude figures out when to call tool_extract_emails, 
# tool_extract_phone_numbers, tool_extract_urls automatically
```

**When to use:** When running browser tasks where Claude should extract data while exploring (recommended).

## How Skills Are Integrated

1. **Registration**: Skills are wrapped with `@tool` decorator in `agent.py`
2. **Binding**: Tools are bound to the Claude LLM via `llm.bind_tools(AGENT_TOOLS)`
3. **Availability**: Claude sees all tools in its system prompt and can invoke them
4. **Auto-calling**: Claude decides when to use tools based on task context

## Example Tasks

### Extract company contact info:
```python
await run_task(
    task="Go to acme-corp.com and use tool_extract_company_info to get all contact info",
)
```

### Compare pricing:
```python
await run_task(
    task="Visit three competing pricing pages. Use tool_parse_pricing to extract and compare their pricing tiers.",
)
```

### Research and summarize:
```python
await run_task(
    task="Research AI trends. Use tool_summarize to create a 3-sentence summary of key findings.",
    instructions=RESEARCH_INSTRUCTIONS,
)
```

## Running Demos

### Direct skill usage:
```bash
python skills_demo.py
```

### Skills + Instructions + Sub-agents:
```bash
python demo_extended.py
```

## Creating New Skills

To add a new skill:

1. Add the function to `skills.py`:
```python
def extract_custom_data(text: str) -> dict:
    """Extract custom data from text."""
    # Implementation
    return result
```

2. Wrap it in `agent.py`:
```python
@tool
def tool_extract_custom_data(text: str) -> dict:
    """Extract custom data from text."""
    return extract_custom_data(text)
```

3. Add to `AGENT_TOOLS` list:
```python
AGENT_TOOLS = [
    # ... existing tools
    tool_extract_custom_data,
]
```

4. Claude will automatically have access to the new skill in future tasks.
