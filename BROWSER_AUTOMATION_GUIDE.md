# Browser Automation Guide

Complete guide to using browser automation in Claude Managed Agents.

## Overview

Your agents now have built-in browser automation capabilities powered by:
- **browser-use**: High-level browser agent
- **Playwright**: Browser automation framework
- **Chromium**: Headless browser engine (runs without GUI)

## Quick Start

### Example 1: Visit Website and Extract Data

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com and extract all product names and prices"
  }'
```

### Example 2: Generate Scraping Code

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com and generate Python BeautifulSoup code to scrape product data"
  }'
```

### Example 3: Automate Forms

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Visit https://example.com/search, fill search box with \"python\", click search, and extract top 5 results"
  }'
```

## How It Works

### Architecture

```
Agent Container
├─ Claude Brain (Anthropic SDK)
├─ Tools:
│  ├─ extract_structured_data (regex)
│  ├─ query_database (SQL)
│  ├─ call_external_api (HTTP)
│  └─ browse_web (Playwright) ← NEW!
│     ├─ Chromium (headless)
│     └─ JavaScript execution
└─ /workspace, /memory (isolated volumes)
```

### Headless Browser

**Headless means**:
- No visual GUI (no window displayed)
- Runs perfectly in Docker containers
- Uses less memory (~200MB per browser)
- Faster execution
- Can take screenshots and extract text

**Still supports**:
- ✅ Navigation (HTTP/HTTPS)
- ✅ JavaScript execution
- ✅ Form filling & clicking
- ✅ Screenshots (PNG)
- ✅ Text extraction
- ✅ Dynamic content loading
- ✅ Cookie handling
- ✅ User-Agent control

## Tool Parameters

### browse_web()

Required:
- `url` (str): Website to visit (e.g., "https://example.com")
- `task` (str): What to do on the website

Optional:
- `screenshot` (bool): Capture page screenshot (default: false)
- `extract_text` (bool): Extract page text (default: true)
- `extract_links` (bool): Extract all links (default: false)
- `timeout` (int): Max seconds (default: 30, max: 120)

### Example Usage

```python
# Task for Claude
"""
Visit https://news.ycombinator.com and:
1. Take a screenshot
2. Extract all story titles and upvote counts
3. Generate Python code to automate this scraping
"""

# This calls browse_web with:
{
    "url": "https://news.ycombinator.com",
    "task": "Extract story titles and upvote counts",
    "screenshot": True,
    "extract_text": True,
    "timeout": 30
}

# Claude receives:
{
    "url": "...",
    "result": "Successfully extracted...",
    "page_text": "...",
    "links": [...],
    "screenshot": "data:image/png;base64,..."
}

# Claude then:
# - Analyzes the page content
# - Generates extraction code
# - Returns both code and results
```

## Real-World Examples

### E-commerce Price Monitoring

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{
    "task": "Visit https://store.example.com/product/laptop, extract price, availability, and customer rating. Generate code to monitor price changes daily."
  }'
```

### Job Listing Scraper

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{
    "task": "Visit https://jobs.example.com, search for \"python\", and extract job title, company, location, and salary for top 20 results. Generate Selenium code for automation."
  }'
```

### Data Migration

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{
    "task": "Visit https://old-site.example.com, extract all user records (name, email, phone), and return code to migrate to our database"
  }'
```

### Content Aggregation

```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{
    "task": "Visit https://news-site.example.com, https://tech-blog.example.com, and https://reddit.com/r/python, extract headlines from all, combine, and generate summary code"
  }'
```

## What Claude Can Generate

When you ask Claude to "generate code", it creates:

### BeautifulSoup (HTML Parsing)

```python
from bs4 import BeautifulSoup
import requests

response = requests.get('https://example.com')
soup = BeautifulSoup(response.content, 'html.parser')

products = []
for item in soup.find_all('div', class_='product'):
    name = item.find('h2').text
    price = item.find('span', class_='price').text
    products.append({'name': name, 'price': price})
```

### Selenium (Browser Automation)

```python
from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Chrome()
driver.get('https://example.com')

# Fill search
search = driver.find_element(By.ID, 'search')
search.send_keys('python')
search.submit()

# Extract results
results = driver.find_elements(By.CLASS_NAME, 'result')
for result in results[:5]:
    print(result.text)
```

### Playwright (Modern Automation)

```python
import asyncio
from playwright.async_api import async_playwright

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://example.com')
        
        content = await page.content()
        text = await page.inner_text('body')
        
        await browser.close()
```

## Performance & Limits

### Resource Usage

| Task Type | Memory | CPU | Time |
|-----------|--------|-----|------|
| Text extraction | 150MB | 10% | 5-10s |
| Form filling | 200MB | 20% | 10-20s |
| Dynamic content | 250MB | 50% | 15-30s |
| Screenshot | 300MB | 60% | 10-25s |

### Limits

- **Timeout**: 30-120 seconds (configurable)
- **Memory**: 2GB per container
- **CPU**: 1 core per container
- **Screenshot size**: Up to 10MB
- **Text extraction**: First 5000 chars

### Container Limits for Browser Work

If running browser-heavy tasks, increase limits:

```yaml
# docker-compose.yml
orchestrator:
  environment:
    - MEM_LIMIT=4g  # Increase from 2g
    - CPU_LIMIT=2   # Increase from 1
```

## Multi-Agent Browser Tasks

Run multiple browser tasks in parallel:

```bash
# Create 3 agents
for i in {1..3}; do
  curl -s -X POST http://localhost:8000/agents/create \
    -d "{\"name\":\"browser-agent-$i\"}" | jq -r '.agent_id'
done

# Submit browser tasks to all simultaneously
# Each runs in isolated container
# Each has its own browser instance
# All run in parallel!
```

## Troubleshooting

### Browser Task Times Out

```bash
# Increase timeout
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{
    "task": "...",
    "timeout": 120
  }'
```

### Page Not Loading

Check if site allows:
- Headless browsers (some sites block)
- Requests from cloud providers
- JavaScript rendering

Try:
```bash
curl -X POST http://localhost:8000/agents/{agent_id}/task \
  -d '{
    "task": "Visit {url} and check if page loads. If JavaScript fails, extract raw HTML."
  }'
```

### Memory Issues

Browser tasks use more memory. Check:
```bash
docker stats agent-{short_id}  # Monitor usage
```

Reduce concurrent browser tasks or increase agent memory limit.

## Security Considerations

✅ **Safe**:
- Headless execution (no GUI access)
- Sandboxed in container
- Isolated volumes
- Resource limits
- Timeout protection

⚠️ **Be Careful**:
- Some sites may block automated access
- Respect robots.txt and ToS
- Don't overload servers with many requests
- Credentials in tasks appear in logs

## Advanced: Custom Browser Tools

Extend browser automation:

```python
# tools/custom_tools.py

async def advanced_browser_task(args):
    """Custom browser automation."""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Your custom logic
        await page.goto(args['url'])
        await page.click(args['selector'])
        
        result = await page.inner_text('body')
        await browser.close()
        
        return {"content": [{"type": "text", "text": result}]}
```

## FAQ

**Q: Is the browser visible on screen?**
A: No, it runs headless (no GUI). This is intentional for Docker.

**Q: Can I run multiple browsers at once?**
A: Yes! Each agent has its own isolated browser instance.

**Q: What sites can I access?**
A: Most public websites. Some may block automated access.

**Q: Can I use the browser to fill in forms?**
A: Yes! Claude can automate form filling, clicking, scrolling, etc.

**Q: How long can browser tasks run?**
A: Up to 120 seconds (configurable).

**Q: Can it handle JavaScript-heavy sites?**
A: Yes, Playwright executes JavaScript automatically.

**Q: Can it take screenshots?**
A: Yes, request screenshot=true in task.

**Q: Can it extract both text and links?**
A: Yes, request extract_text=true and extract_links=true.

---

**For more details**, see:
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [README.md](README.md) - Quick start & examples
- [ORCHESTRATOR_GUIDE.md](ORCHESTRATOR_GUIDE.md) - Deep technical details
- [GETTING_STARTED.md](GETTING_STARTED.md) - Setup & customization

---

**Last Updated**: 2026-04-28
