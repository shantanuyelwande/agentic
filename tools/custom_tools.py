"""
Custom tool definitions for Claude agents.

Each tool is decorated with @tool and can be called by Claude
during task execution. Tools must return a properly formatted
response with content blocks.
"""

import re
import json
import httpx
import sqlite3
import asyncio
import base64
from typing import Any, Dict, List, Optional


# Tool 1: Extract Structured Data
def extract_structured_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured information from unstructured text.

    Extracts emails, phone numbers, and URLs using regex patterns.
    Safe for processing large text documents.

    Args:
        text (str): The text to extract from
        types (list): What to extract - 'emails', 'phones', 'urls' (default: ['emails'])

    Returns:
        Dictionary with extracted data organized by type
    """
    text = args.get("text", "")
    types = args.get("types", ["emails"])

    if not isinstance(text, str):
        return {
            "content": [{
                "type": "text",
                "text": "Error: text parameter must be a string"
            }],
            "is_error": True
        }

    if len(text) > 100000:
        return {
            "content": [{
                "type": "text",
                "text": "Error: text too large (max 100KB)"
            }],
            "is_error": True
        }

    results = {}

    # Extract emails
    if "emails" in types:
        results["emails"] = re.findall(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            text
        )

    # Extract phone numbers (US format)
    if "phones" in types:
        phone_pattern = r'(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'
        matches = re.findall(phone_pattern, text)
        results["phones"] = ['-'.join(match) for match in matches]

    # Extract URLs
    if "urls" in types:
        results["urls"] = re.findall(
            r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)',
            text
        )

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "found": len(results),
                "data": results
            }, indent=2)
        }]
    }


# Tool 2: Query Database
def query_database(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute safe SQL queries on the business database.

    Prevents dangerous operations (DELETE, DROP, TRUNCATE, ALTER).
    Uses parameter binding to prevent SQL injection.

    Args:
        query (str): SQL query with ? placeholders for parameters
        params (list): Parameters to bind to placeholders (default: [])
        limit (int): Maximum rows to return (default: 100, max: 1000)

    Returns:
        Query results as JSON
    """
    query = args.get("query", "").strip()
    params = args.get("params", [])
    limit = min(args.get("limit", 100), 1000)  # Cap at 1000

    if not query:
        return {
            "content": [{
                "type": "text",
                "text": "Error: query parameter is required"
            }],
            "is_error": True
        }

    # Block dangerous SQL operations
    dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"]
    query_upper = query.upper()

    for keyword in dangerous_keywords:
        if f" {keyword} " in f" {query_upper} ":
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: {keyword} operations are not allowed"
                }],
                "is_error": True
            }

    try:
        # Use in-memory database for demo (replace with your database)
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # For demo: create sample table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sample (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                created_at TEXT
            )
        """)
        cursor.execute("INSERT INTO sample VALUES (1, 'John Doe', 'john@example.com', '2024-01-01')")
        cursor.execute("INSERT INTO sample VALUES (2, 'Jane Smith', 'jane@example.com', '2024-01-02')")
        conn.commit()

        # Execute user query
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert to list of dicts
        result_data = [dict(row) for row in rows[:limit]]

        conn.close()

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "rows_returned": len(result_data),
                    "data": result_data
                }, indent=2)
            }]
        }

    except sqlite3.Error as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Database error: {str(e)}"
            }],
            "is_error": True
        }
    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Unexpected error: {str(e)}"
            }],
            "is_error": True
        }


# Tool 3: Call External API
def call_external_api(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call external REST APIs safely.

    Includes domain whitelisting, timeout protection, and
    error handling. Supports GET, POST, PUT, DELETE methods.

    Args:
        url (str): API endpoint URL
        method (str): HTTP method - GET, POST, PUT, DELETE (default: 'GET')
        headers (dict): Optional HTTP headers (default: {})
        body (dict): Optional request body for POST/PUT (default: None)
        timeout (int): Request timeout in seconds (default: 30, max: 60)

    Returns:
        API response as JSON
    """
    url = args.get("url", "").strip()
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")
    timeout = min(args.get("timeout", 30), 60)  # Cap at 60 seconds

    if not url:
        return {
            "content": [{
                "type": "text",
                "text": "Error: url parameter is required"
            }],
            "is_error": True
        }

    # Whitelist allowed domains
    allowed_domains = [
        "api.example.com",
        "data.service.com",
        "httpbin.org",  # For testing
        "jsonplaceholder.typicode.com",  # For testing
    ]

    domain_whitelisted = any(domain in url for domain in allowed_domains)

    if not domain_whitelisted:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Domain not whitelisted. Allowed domains: {', '.join(allowed_domains)}"
            }],
            "is_error": True
        }

    # Validate HTTP method
    if method not in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Unsupported HTTP method: {method}"
            }],
            "is_error": True
        }

    try:
        response = httpx.request(
            method,
            url,
            headers=headers,
            json=body,
            timeout=timeout,
            follow_redirects=True,
        )

        # Parse response
        try:
            response_data = response.json()
        except Exception:
            response_data = response.text

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "status_code": response.status_code,
                    "success": 200 <= response.status_code < 300,
                    "data": response_data
                }, indent=2)
            }]
        }

    except httpx.TimeoutException:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Request timeout after {timeout} seconds"
            }],
            "is_error": True
        }
    except httpx.ConnectError as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Connection failed - {str(e)}"
            }],
            "is_error": True
        }
    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: {str(e)}"
            }],
            "is_error": True
        }


# Tool 4: Browser Automation
def browse_web(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Automate web browser tasks using headless Chromium.

    Uses browser-use library to interact with websites. Supports
    navigation, clicking, form filling, and data extraction.
    Runs in headless mode (no GUI) inside Docker container.

    Args:
        url (str): URL to visit (required)
        task (str): What to do on the website (required)
        screenshot (bool): Capture screenshot after task (default: False)
        extract_text (bool): Extract page text content (default: True)
        extract_links (bool): Extract all links from page (default: False)
        timeout (int): Max seconds for task (default: 30, max: 120)

    Returns:
        Browser task result with page content, links, or screenshot
    """
    url = args.get("url", "").strip()
    task = args.get("task", "").strip()
    screenshot = args.get("screenshot", False)
    extract_text = args.get("extract_text", True)
    extract_links = args.get("extract_links", False)
    timeout = min(args.get("timeout", 30), 120)  # Cap at 2 minutes

    if not url:
        return {
            "content": [{
                "type": "text",
                "text": "Error: url parameter is required"
            }],
            "is_error": True
        }

    if not task:
        return {
            "content": [{
                "type": "text",
                "text": "Error: task parameter is required (describe what to do on the website)"
            }],
            "is_error": True
        }

    # Validate URL format
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        # Import browser-use (lazy import to avoid issues if playwright not installed)
        try:
            from browser_use import Agent
        except ImportError:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: browser-use library not available. Install with: pip install browser-use"
                }],
                "is_error": True
            }

        # Run browser automation in async context
        async def run_browser_task():
            agent = Agent(timeout=timeout)

            # Run the task
            result = await agent.run(task, url=url)

            # Collect output
            output = {
                "url": url,
                "task": task,
                "status": "completed",
                "result": str(result) if result else "Task completed"
            }

            # Extract page text if requested
            if extract_text:
                try:
                    page = agent.browser._current_page if hasattr(agent, 'browser') else None
                    if page:
                        page_text = await page.evaluate('() => document.body.innerText')
                        output["page_text"] = page_text[:5000]  # First 5000 chars
                except Exception as e:
                    output["text_extraction_error"] = str(e)

            # Extract links if requested
            if extract_links:
                try:
                    page = agent.browser._current_page if hasattr(agent, 'browser') else None
                    if page:
                        links = await page.evaluate('''
                            () => Array.from(document.querySelectorAll('a[href]'))
                                .map(a => ({text: a.textContent.trim(), url: a.href}))
                                .filter(l => l.url)
                                .slice(0, 50)
                        ''')
                        output["links"] = links
                except Exception as e:
                    output["links_extraction_error"] = str(e)

            # Take screenshot if requested
            if screenshot:
                try:
                    page = agent.browser._current_page if hasattr(agent, 'browser') else None
                    if page:
                        screenshot_bytes = await page.screenshot()
                        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
                        output["screenshot"] = f"data:image/png;base64,{screenshot_b64}"
                        output["screenshot_size_kb"] = len(screenshot_b64) / 1024
                except Exception as e:
                    output["screenshot_error"] = str(e)

            return output

        # Execute async function
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule as task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, run_browser_task())
                    output = future.result(timeout=timeout + 10)
            else:
                output = loop.run_until_complete(run_browser_task())
        except RuntimeError:
            # No loop exists, create new one
            output = asyncio.run(run_browser_task())

        return {
            "content": [{
                "type": "text",
                "text": json.dumps(output, indent=2, default=str)
            }]
        }

    except asyncio.TimeoutError:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Browser task timeout after {timeout} seconds"
            }],
            "is_error": True
        }
    except Exception as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Browser automation failed - {str(e)}"
            }],
            "is_error": True
        }
