"""
LangChain Tools for LangGraph Deep Agent

Each function is decorated with @tool so LangGraph's executor can discover
and call them automatically during the Plan-and-Execute loop.
"""

import json
import re
import subprocess
from typing import Optional
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool

# Domains allowed for the call_external_api tool
_ALLOWED_DOMAINS = {
    "api.example.com",
    "data.service.com",
    "httpbin.org",
    "jsonplaceholder.typicode.com",
}

# Commands that must never run
_BLOCKED_PATTERNS = [
    "rm -rf",
    "dd if=",
    "> /dev/",
    "mkfs",
    "fdisk",
    "shutdown",
    "reboot",
    ":(){:|:&};:",  # fork bomb
]


@tool
def web_search(query: str) -> str:
    """Search the web for information on a topic and return a summary of results.

    Args:
        query: The search query string.
    """
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        resp = httpx.get(url, params=params, timeout=30, follow_redirects=True)
        data = resp.json()

        lines = []
        if data.get("Abstract"):
            lines.append(f"Summary: {data['Abstract']}")
        if data.get("AbstractURL"):
            lines.append(f"Source: {data['AbstractURL']}")

        for topic in data.get("RelatedTopics", [])[:6]:
            if isinstance(topic, dict) and topic.get("Text"):
                lines.append(f"- {topic['Text']}")

        return "\n".join(lines) if lines else f"No results found for: {query}"

    except Exception as exc:
        return f"Search failed: {exc}"


@tool
def web_fetch(url: str) -> str:
    """Fetch the text content of a webpage or JSON endpoint.

    Args:
        url: Full URL (http/https) to fetch.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; LangGraphAgent/1.0)"}
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return json.dumps(resp.json(), indent=2)[:12000]

        # Strip HTML tags
        text = resp.text
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:12000]

    except Exception as exc:
        return f"Fetch failed for {url}: {exc}"


@tool
def extract_structured_data(text: str) -> str:
    """Extract emails, phone numbers, and URLs from arbitrary text.

    Args:
        text: Raw text to parse (max 100 KB processed).

    Returns:
        JSON string with keys: emails, phone_numbers, urls.
    """
    text = text[:100_000]

    result = {
        "emails": list(
            set(re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text))
        ),
        "phone_numbers": list(
            set(re.findall(r"[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]", text))
        )[:20],
        "urls": list(
            set(re.findall(r"https?://[^\s<>\"{}|\\^`\[\]]+", text))
        )[:50],
    }
    return json.dumps(result, indent=2)


@tool
def run_bash(command: str) -> str:
    """Execute a bash command and return stdout + stderr (60-second timeout).

    Use for file operations, data processing, or running scripts.
    Destructive commands (rm -rf, shutdown, etc.) are blocked.

    Args:
        command: Shell command to run.
    """
    for pattern in _BLOCKED_PATTERNS:
        if pattern in command:
            return f"Blocked: command contains forbidden pattern '{pattern}'"

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = proc.stdout
        if proc.stderr:
            output += f"\nSTDERR:\n{proc.stderr}"
        return output[:12000] or "(no output)"

    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds."
    except Exception as exc:
        return f"Command failed: {exc}"


@tool
def call_external_api(
    url: str,
    method: str = "GET",
    body: Optional[str] = None,
) -> str:
    """Call an external HTTP API and return the response body.

    Allowed domains: httpbin.org, jsonplaceholder.typicode.com,
    api.example.com, data.service.com.

    Args:
        url:    Full endpoint URL.
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, HEAD).
        body:   Optional JSON string for POST/PUT/PATCH requests.
    """
    domain = urlparse(url).netloc.lower()
    if not any(domain == d or domain.endswith("." + d) for d in _ALLOWED_DOMAINS):
        return (
            f"Domain '{domain}' is not in the allowlist. "
            f"Allowed: {', '.join(sorted(_ALLOWED_DOMAINS))}"
        )

    method = method.upper()
    allowed_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}
    if method not in allowed_methods:
        return f"Method '{method}' not allowed. Use one of: {', '.join(sorted(allowed_methods))}"

    try:
        kwargs: dict = {"timeout": 60, "follow_redirects": True}
        if body and method in {"POST", "PUT", "PATCH"}:
            try:
                kwargs["json"] = json.loads(body)
            except json.JSONDecodeError:
                kwargs["content"] = body.encode()

        resp = httpx.request(method, url, **kwargs)
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return json.dumps(resp.json(), indent=2)[:12000]
        return resp.text[:12000]

    except Exception as exc:
        return f"API call failed: {exc}"


def get_all_tools() -> list:
    """Return all registered LangChain tools."""
    return [
        web_search,
        web_fetch,
        extract_structured_data,
        run_bash,
        call_external_api,
    ]
