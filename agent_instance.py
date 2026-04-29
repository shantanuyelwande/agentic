"""
Claude Agent Instance

Runs inside an isolated container. Uses Claude Agent SDK as the brain
and executes custom tools. Maintains session state and returns results.

Environment Variables:
  - AGENT_ID: Unique agent identifier
  - ANTHROPIC_API_KEY: API key for Claude
"""

import asyncio
import os
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from anthropic import Anthropic
from dotenv import load_dotenv
import structlog

from tools.custom_tools import (
    extract_structured_data,
    query_database,
    call_external_api,
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
AGENT_ID = os.getenv("AGENT_ID", "default-agent")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
WORKSPACE = Path("/workspace")
MEMORY = Path("/memory")

# Ensure directories exist
WORKSPACE.mkdir(parents=True, exist_ok=True)
MEMORY.mkdir(parents=True, exist_ok=True)


def load_skills_context() -> str:
    """Load skills from .claude/skills/ directory."""
    skills_dir = Path(".claude/skills")
    if not skills_dir.exists():
        return ""

    logger.info("loading_skills", skills_dir=str(skills_dir))

    skills_context = "# Available Skills\n\n"
    skill_docs = []

    try:
        for skill_path in sorted(skills_dir.iterdir()):
            if skill_path.is_dir():
                skill_md = skill_path / "SKILL.md"
                if skill_md.exists():
                    logger.info("found_skill", skill_name=skill_path.name)
                    skill_docs.append(skill_md.read_text())
    except Exception as e:
        logger.warning("error_loading_skills", error=str(e))

    if skill_docs:
        skills_context += "\n\n---\n\n".join(skill_docs)
        logger.info("skills_loaded", count=len(skill_docs))
        return skills_context

    return ""


def load_session_context() -> Dict[str, Any]:
    """Load previous session context if it exists."""
    session_file = MEMORY / "session.json"

    if session_file.exists():
        try:
            return json.loads(session_file.read_text())
        except Exception as e:
            logger.warning("error_loading_session", error=str(e))

    return {
        "agent_id": AGENT_ID,
        "messages": [],
        "tool_calls": [],
        "created_at": datetime.now().isoformat(),
    }


def save_session_context(session: Dict[str, Any]) -> None:
    """Save session context for future use."""
    session_file = MEMORY / "session.json"
    try:
        session_file.write_text(json.dumps(session, indent=2))
        logger.info("session_saved", session_id=session.get("agent_id"))
    except Exception as e:
        logger.error("error_saving_session", error=str(e))


async def run_agent() -> Dict[str, Any]:
    """
    Main agent loop.

    Reads task from workspace, uses Claude to process it with tools,
    returns results and saves state.
    """

    logger.info("agent_starting", agent_id=AGENT_ID)

    # Check if API key is set
    if not ANTHROPIC_API_KEY:
        error_msg = "ANTHROPIC_API_KEY not set"
        logger.error("missing_api_key")
        return {
            "agent_id": AGENT_ID,
            "status": "failed",
            "error": error_msg,
        }

    # Read task from input file
    task_file = WORKSPACE / "task.json"
    if not task_file.exists():
        error_msg = "No task file found at /workspace/task.json"
        logger.error("no_task_file")
        return {
            "agent_id": AGENT_ID,
            "status": "failed",
            "error": error_msg,
        }

    try:
        task_data = json.loads(task_file.read_text())
        task = task_data.get("task", "")
        task_id = task_data.get("task_id", "unknown")
    except Exception as e:
        error_msg = f"Error reading task file: {str(e)}"
        logger.error("error_reading_task", error=str(e))
        return {
            "agent_id": AGENT_ID,
            "status": "failed",
            "error": error_msg,
        }

    if not task:
        error_msg = "Task is empty"
        logger.error("empty_task")
        return {
            "agent_id": AGENT_ID,
            "status": "failed",
            "error": error_msg,
        }

    logger.info("task_received", task_id=task_id, task_preview=task[:50])

    # Load session and skills
    session = load_session_context()
    skills_context = load_skills_context()

    # Build full task with context
    full_task = task
    if skills_context:
        full_task = f"{skills_context}\n\n---\n\n## Your Task\n\n{task}"

    # Initialize result structure
    result = {
        "agent_id": AGENT_ID,
        "task_id": task_id,
        "task": task,
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "messages": [],
        "tool_calls": [],
        "final_output": "",
        "error": None,
    }

    try:
        logger.info("initializing_claude_api")

        # Initialize Anthropic client
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        # Store tool results
        tool_results = {}

        # Agentic loop - Claude decides which tools to use
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info("agent_iteration", iteration=iteration)

            # Call Claude
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": full_task,
                    }
                ],
            )

            # Process response
            for block in response.content:
                if hasattr(block, "text"):
                    result["final_output"] += block.text
                    result["messages"].append({
                        "type": "assistant",
                        "content": block.text,
                    })
                    logger.info("claude_response", length=len(block.text))

                elif hasattr(block, "type") and block.type == "tool_use":
                    # Handle tool use
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    logger.info("tool_use_requested", tool=tool_name)

                    result["tool_calls"].append({
                        "name": tool_name,
                        "input": tool_input,
                        "id": tool_use_id,
                    })

                    # Execute tool
                    tool_result = await execute_tool(tool_name, tool_input)
                    tool_results[tool_use_id] = tool_result

                    logger.info("tool_executed", tool=tool_name, success=not tool_result.get("is_error", False))

            # Check if we should continue
            if response.stop_reason == "end_turn":
                logger.info("agent_finished")
                break

            if response.stop_reason != "tool_use":
                logger.info("agent_finished", stop_reason=response.stop_reason)
                break

        result["status"] = "completed"
        result["finished_at"] = datetime.now().isoformat()

        logger.info("agent_completed", status="success")

    except Exception as e:
        logger.error("agent_error", error=str(e))
        result["status"] = "failed"
        result["error"] = str(e)
        result["finished_at"] = datetime.now().isoformat()

    # Save results
    output_file = WORKSPACE / "output.json"
    try:
        output_file.write_text(json.dumps(result, indent=2))
        logger.info("output_saved", output_file=str(output_file))
    except Exception as e:
        logger.error("error_saving_output", error=str(e))

    # Update and save session
    session["messages"] = result["messages"]
    session["tool_calls"] = result["tool_calls"]
    session["updated_at"] = datetime.now().isoformat()
    save_session_context(session)

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


def main():
    """Entry point."""
    try:
        result = asyncio.run(run_agent())
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "completed" else 1)
    except KeyboardInterrupt:
        logger.info("agent_interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("agent_fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
