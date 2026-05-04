"""
Claude Agent Instance

Uses Claude Agent SDK to build an autonomous agent that:
- Loads skills from .claude/skills/ directory
- Accepts task_data dict (replaces file I/O)
- Returns structured result dict
- Supports Redis checkpointing for fault tolerance
- Respects configurable step budgets
"""

import asyncio
import os
import sys
import json
import redis
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from anthropic import Anthropic
from dotenv import load_dotenv
import yaml
import structlog

from tools.custom_tools import (
    extract_structured_data,
    query_database,
    call_external_api,
    read_file,
)

# Load environment
load_dotenv(override=True)

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SKILLS_DIR = Path(os.getenv("SKILLS_DIR", "/app/.claude/skills"))
CHECKPOINT_INTERVAL = int(os.getenv("CHECKPOINT_INTERVAL", 3))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Redis client (optional, for checkpointing)
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception:
    redis_client = None


def _parse_skill_frontmatter(file_path: Path) -> Optional[Dict[str, str]]:
    """
    Parse YAML frontmatter from SKILL.md file.

    Returns:
        Dict with 'name' and 'description', or None if parsing fails
    """
    try:
        content = file_path.read_text()
        if not content.startswith("---"):
            return None

        # Extract frontmatter between first and second ---
        _, frontmatter, _ = content.split("---", 2)

        # Parse YAML
        metadata = yaml.safe_load(frontmatter)
        if isinstance(metadata, dict) and "name" in metadata and "description" in metadata:
            return {
                "name": metadata["name"],
                "description": metadata["description"],
            }
    except Exception as e:
        logger.warning("error_parsing_frontmatter", file=str(file_path), error=str(e))

    return None


def _load_skills_index() -> str:
    """
    Load skills metadata (progressive disclosure).

    Returns formatted text listing available skills.
    Each skill includes name, description, and file path.
    """
    if not SKILLS_DIR.exists():
        return ""

    logger.info("loading_skills_index", skills_dir=str(SKILLS_DIR))

    skills_index = "# Available Skills\n\n"
    skills_index += "You have domain expertise available in the following skills. "
    skills_index += "When a task matches a skill's description, use the read_file tool to load its full instructions.\n\n"

    skill_entries = []

    try:
        for skill_path in sorted(SKILLS_DIR.iterdir()):
            if skill_path.is_dir():
                skill_md = skill_path / "SKILL.md"
                if skill_md.exists():
                    metadata = _parse_skill_frontmatter(skill_md)
                    if metadata:
                        entry = (
                            f"## {metadata['name']}\n"
                            f"Description: {metadata['description']}\n"
                            f"File: {skill_md}\n"
                        )
                        skill_entries.append(entry)
                        logger.info("found_skill", name=metadata["name"])
    except Exception as e:
        logger.warning("error_loading_skills_index", error=str(e))

    if skill_entries:
        skills_index += "\n".join(skill_entries)
        logger.info("skills_index_loaded", count=len(skill_entries))
        return skills_index

    return ""


def _save_checkpoint(task_id: str, progress: Dict[str, Any]) -> None:
    """Save checkpoint to Redis for fault tolerance."""
    if not redis_client:
        return

    try:
        checkpoint_key = f"checkpoint:{task_id}"
        redis_client.setex(
            checkpoint_key,
            3600,  # 1 hour TTL
            json.dumps(progress, default=str)
        )
        logger.debug("checkpoint_saved", task_id=task_id, iteration=progress.get("iteration"))
    except Exception as e:
        logger.warning("error_saving_checkpoint", error=str(e))


def _load_checkpoint(task_id: str) -> Optional[Dict[str, Any]]:
    """Load checkpoint from Redis if available."""
    if not redis_client:
        return None

    try:
        checkpoint_key = f"checkpoint:{task_id}"
        data = redis_client.get(checkpoint_key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning("error_loading_checkpoint", error=str(e))

    return None


def _clear_checkpoint(task_id: str) -> None:
    """Clear checkpoint from Redis."""
    if not redis_client:
        return

    try:
        checkpoint_key = f"checkpoint:{task_id}"
        redis_client.delete(checkpoint_key)
    except Exception as e:
        logger.warning("error_clearing_checkpoint", error=str(e))


async def run_agent(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run Claude agent on a task.

    Args:
        task_data: Dict containing:
            - task (str): Task description
            - task_id (str): Unique task ID
            - max_steps (int, optional): Max iterations (default 10)
            - timeout (int, optional): Timeout in seconds

    Returns:
        Dict with keys: status, result, steps_taken, duration_seconds, error
    """
    task = task_data.get("task", "")
    task_id = task_data.get("task_id", "unknown")
    max_steps = task_data.get("max_steps", 10)
    start_time = datetime.now(timezone.utc)

    logger.info(
        "agent_starting",
        task_id=task_id,
        max_steps=max_steps,
        input_preview=task[:50]
    )

    # Check API key
    if not ANTHROPIC_API_KEY:
        error_msg = "ANTHROPIC_API_KEY not set"
        logger.error("missing_api_key")
        return {
            "status": "failed",
            "result": "",
            "steps_taken": 0,
            "duration_seconds": 0,
            "error": error_msg,
        }

    # Load skills index and build system prompt
    skills_index = _load_skills_index()
    system_prompt = (
        "You are Claude, a helpful AI assistant. "
        "You have access to tools for extracting data, querying databases, and calling APIs.\n\n"
    )
    if skills_index:
        system_prompt += skills_index + "\n\n"

    # Initialize result structure
    result = {
        "status": "running",
        "result": "",
        "steps_taken": 0,
        "duration_seconds": 0,
        "error": None,
    }

    try:
        # Initialize Anthropic client
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        # Define tools for Claude
        tools = [
            {
                "name": "extract_structured_data",
                "description": "Extract structured information (emails, phones, URLs) from text",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to extract from"},
                        "types": {"type": "array", "items": {"type": "string"}, "description": "What to extract: emails, phones, urls"}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "query_database",
                "description": "Execute safe SQL queries (SELECT only)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL SELECT query"},
                        "params": {"type": "array", "description": "Query parameters"},
                        "limit": {"type": "integer", "description": "Max rows to return"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "call_external_api",
                "description": "Call external REST APIs (whitelisted domains only)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "API endpoint URL"},
                        "method": {"type": "string", "description": "HTTP method (GET, POST, etc)"},
                        "headers": {"type": "object", "description": "HTTP headers"},
                        "body": {"type": "object", "description": "Request body for POST/PUT"},
                        "timeout": {"type": "integer", "description": "Request timeout in seconds"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "read_file",
                "description": "Read file contents from safe directories (/app/.claude, /workspace, /memory, /tmp)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                        "limit": {"type": "integer", "description": "Max lines to return (default 1000)"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "browse_web",
                "description": "Automate web browser tasks using headless Chromium",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to visit"},
                        "task": {"type": "string", "description": "What to do on the website"},
                        "screenshot": {"type": "boolean", "description": "Capture screenshot"},
                        "extract_text": {"type": "boolean", "description": "Extract page text"},
                        "extract_links": {"type": "boolean", "description": "Extract all links"},
                        "timeout": {"type": "integer", "description": "Max seconds for task"}
                    },
                    "required": ["url", "task"]
                }
            }
        ]

        # Agentic loop
        messages = []
        iteration = 0

        while iteration < max_steps:
            iteration += 1
            logger.info("agent_iteration", iteration=iteration, task_id=task_id)

            # Save checkpoint periodically
            if iteration % CHECKPOINT_INTERVAL == 0:
                _save_checkpoint(task_id, {
                    "iteration": iteration,
                    "messages_count": len(messages),
                    "task_id": task_id,
                })

            # Prepare user message for first iteration
            if iteration == 1:
                user_message = task
            else:
                # Use continue signal for subsequent iterations
                user_message = "Continue processing."

            # Call Claude with tools
            response = client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=[
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ] if iteration == 1 else messages + [
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
            )

            # Add assistant response to messages
            assistant_content = []

            # Process response blocks
            for block in response.content:
                if hasattr(block, "text"):
                    result["result"] += block.text
                    assistant_content.append({
                        "type": "text",
                        "text": block.text,
                    })
                    logger.info("claude_response", length=len(block.text), iteration=iteration)

                elif hasattr(block, "type") and block.type == "tool_use":
                    # Handle tool use
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    logger.info("tool_use_requested", tool=tool_name, iteration=iteration)

                    # Execute tool
                    tool_result = await execute_tool(tool_name, tool_input)

                    assistant_content.append({
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": tool_name,
                        "input": tool_input,
                    })

                    # Add tool result to messages
                    if iteration == 1:
                        messages = [
                            {
                                "role": "user",
                                "content": task,
                            }
                        ]
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": json.dumps(tool_result, default=str),
                            }
                        ],
                    })
                    assistant_content = []

            # Add assistant message to history
            if assistant_content:
                if iteration == 1:
                    messages = [
                        {
                            "role": "user",
                            "content": task,
                        }
                    ]
                messages.append({
                    "role": "assistant",
                    "content": assistant_content,
                })

            # Check if we should continue
            if response.stop_reason == "end_turn":
                logger.info("agent_finished_end_turn", iteration=iteration, task_id=task_id)
                break

            if response.stop_reason != "tool_use":
                logger.info(
                    "agent_finished",
                    stop_reason=response.stop_reason,
                    iteration=iteration,
                    task_id=task_id
                )
                break

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        result["status"] = "completed"
        result["steps_taken"] = iteration
        result["duration_seconds"] = duration

        logger.info(
            "agent_completed",
            task_id=task_id,
            steps=iteration,
            duration=duration,
        )

        # Clear checkpoint on success
        _clear_checkpoint(task_id)

    except Exception as e:
        logger.error("agent_error", task_id=task_id, error=str(e))
        result["status"] = "failed"
        result["error"] = str(e)
        result["steps_taken"] = iteration
        end_time = datetime.now(timezone.utc)
        result["duration_seconds"] = (end_time - start_time).total_seconds()

    return result


async def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a custom tool and return results."""

    logger.info("executing_tool", tool=tool_name, input_keys=list(tool_input.keys()))

    try:
        if tool_name == "extract_structured_data":
            return extract_structured_data(tool_input)

        elif tool_name == "query_database":
            return query_database(tool_input)

        elif tool_name == "call_external_api":
            return call_external_api(tool_input)

        elif tool_name == "read_file":
            return read_file(tool_input)

        elif tool_name == "browse_web":
            from tools.custom_tools import browse_web
            return browse_web(tool_input)

        else:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Unknown tool: {tool_name}"
                }],
                "is_error": True
            }

    except Exception as e:
        logger.error("tool_execution_error", tool=tool_name, error=str(e))
        return {
            "content": [{
                "type": "text",
                "text": f"Tool error: {str(e)}"
            }],
            "is_error": True
        }


async def main_async(task_text: str):
    """Standalone runner for testing."""
    task_data = {
        "task": task_text,
        "task_id": "standalone-" + datetime.now(timezone.utc).isoformat(),
        "max_steps": 10,
        "timeout": 300,
    }
    result = await run_agent(task_data)
    print(json.dumps(result, indent=2))
    return result


def main():
    """Entry point."""
    if len(sys.argv) > 1:
        # Standalone mode: python agent_instance.py "your task here"
        task_text = " ".join(sys.argv[1:])
        result = asyncio.run(main_async(task_text))
        sys.exit(0 if result.get("status") == "completed" else 1)
    else:
        print("Usage: python agent_instance.py 'task description'")
        print("\nExample:")
        print("  python agent_instance.py 'Extract emails from: john@example.com'")
        sys.exit(1)


if __name__ == "__main__":
    main()
