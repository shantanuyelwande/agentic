"""
Agent Orchestrator

Manages Claude agent instances, job queuing, and results persistence.
Each agent runs in an isolated container with its own workspace and memory.

HTTP API for submitting tasks and monitoring agent execution.
"""

import os
import uuid
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import docker
from docker.errors import DockerException
import structlog

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
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
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "claude-agent:latest")
AGENTS_DIR = Path("/data/agents")
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

# Docker client
try:
    docker_client = docker.from_env()
    docker_client.ping()
    logger.info("docker_connected")
except Exception as e:
    logger.error("docker_connection_failed", error=str(e))
    docker_client = None

# FastAPI app
app = FastAPI(
    title="Claude Managed Agents",
    description="Self-hosted Claude-powered agents with container isolation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# In-memory agent registry (use Redis for production)
agents: Dict[str, Dict[str, Any]] = {}


# Pydantic Models
class CreateAgentRequest(BaseModel):
    """Request to create a new agent instance."""
    name: Optional[str] = Field(None, description="Agent name")
    config: Optional[Dict[str, Any]] = Field(None, description="Agent configuration")


class TaskRequest(BaseModel):
    """Request to submit a task to an agent."""
    task: str = Field(..., description="Task description for Claude")
    timeout: int = Field(300, description="Task timeout in seconds", ge=10, le=3600)


class AgentInfo(BaseModel):
    """Information about an agent."""
    agent_id: str
    name: str
    status: str
    created_at: str
    task_count: int


class TaskResult(BaseModel):
    """Result of task execution."""
    task_id: str
    agent_id: str
    status: str
    output: Optional[Dict[str, Any]] = None


# Helper Functions
def get_docker_client():
    """Get Docker client, raise if not available."""
    if not docker_client:
        raise HTTPException(
            status_code=500,
            detail="Docker is not available. Ensure Docker daemon is running."
        )
    return docker_client


def write_task_to_container(container, task_data: Dict[str, Any]) -> None:
    """Write task JSON file to container workspace."""
    try:
        import tarfile
        import io

        # Prepare task file
        task_json = json.dumps(task_data, indent=2).encode()

        # Create tar archive
        info = tarfile.TarInfo(name="task.json")
        info.size = len(task_json)

        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            tar.addfile(tarinfo=info, fileobj=io.BytesIO(task_json))

        tar_buffer.seek(0)

        # Copy to container
        container.put_archive("/workspace", tar_buffer.getvalue())
        logger.info("task_written_to_container", task_id=task_data.get("task_id"))

    except Exception as e:
        logger.error("error_writing_task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to write task to container: {str(e)}")


async def execute_task_in_container(
    agent_id: str,
    task_id: str,
    container,
) -> None:
    """Execute task in agent container (background task)."""
    logger.info("executing_task_in_background", agent_id=agent_id, task_id=task_id)

    try:
        # Run agent
        exit_code, output = container.exec_run(
            "python /app/agent_instance.py",
            stdout=True,
            stderr=True,
            demux=False,
        )

        logger.info(
            "task_executed",
            agent_id=agent_id,
            task_id=task_id,
            exit_code=exit_code
        )

        # Update task status
        if agent_id in agents:
            for task in agents[agent_id]["tasks"]:
                if task["task_id"] == task_id:
                    task["status"] = "completed" if exit_code == 0 else "failed"
                    task["completed_at"] = datetime.now().isoformat()
                    break

    except Exception as e:
        logger.error("task_execution_error", error=str(e), agent_id=agent_id, task_id=task_id)
        if agent_id in agents:
            for task in agents[agent_id]["tasks"]:
                if task["task_id"] == task_id:
                    task["status"] = "failed"
                    task["error"] = str(e)
                    break


# API Endpoints

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "docker_available": docker_client is not None,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/agents/create", response_model=Dict[str, Any])
async def create_agent(request: CreateAgentRequest):
    """
    Create a new isolated agent instance.

    Each agent runs in its own Docker container with isolated
    workspace and memory volumes.

    Returns:
        agent_id: Unique identifier for the agent
        status: Creation status
        container_id: Docker container ID
    """
    client = get_docker_client()

    agent_id = str(uuid.uuid4())

    logger.info("creating_agent", agent_id=agent_id, agent_name=request.name)

    try:
        # Create volumes for agent
        ws_volume = client.volumes.create(name=f"agent-{agent_id}-ws")
        mem_volume = client.volumes.create(name=f"agent-{agent_id}-mem")

        logger.info("volumes_created", agent_id=agent_id, ws_vol=ws_volume.name, mem_vol=mem_volume.name)

        # Start container
        container = client.containers.run(
            DOCKER_IMAGE,
            detach=True,
            name=f"agent-{agent_id[:8]}",
            environment={
                "AGENT_ID": agent_id,
                "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
            },
            volumes={
                ws_volume.name: {"bind": "/workspace", "mode": "rw"},
                mem_volume.name: {"bind": "/memory", "mode": "rw"},
            },
            mem_limit="2g",
            cpu_quota=100000,
            cpu_period=100000,
            healthcheck={
                "test": ["CMD", "python", "-c", "import sys; sys.exit(0)"],
                "interval": 30000000000,  # 30 seconds in nanoseconds
                "timeout": 10000000000,   # 10 seconds in nanoseconds
                "retries": 3,
            },
        )

        logger.info("container_started", agent_id=agent_id, container_id=container.id[:12])

        # Store agent info
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

        return {
            "agent_id": agent_id,
            "name": agents[agent_id]["name"],
            "status": "created",
            "container_id": container.id[:12],
            "created_at": agents[agent_id]["created_at"],
        }

    except Exception as e:
        logger.error("agent_creation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@app.post("/agents/{agent_id}/task", response_model=Dict[str, Any])
async def submit_task(agent_id: str, request: TaskRequest, background_tasks: BackgroundTasks):
    """
    Submit a task to an agent for execution.

    Claude will process the task, decide which tools to use,
    and return results. Task runs asynchronously in background.

    Returns:
        task_id: Unique task identifier
        status: Task status (submitted, running, completed, failed)
    """
    if agent_id not in agents:
        logger.warning("agent_not_found", agent_id=agent_id)
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]
    task_id = str(uuid.uuid4())

    logger.info("submitting_task", agent_id=agent_id, task_id=task_id, task_preview=request.task[:50])

    try:
        # Get container
        container = docker_client.containers.get(agent["container_id"])

        # Write task file
        task_data = {
            "task_id": task_id,
            "task": request.task,
            "timeout": request.timeout,
        }
        write_task_to_container(container, task_data)

        # Store task reference
        agents[agent_id]["tasks"].append({
            "task_id": task_id,
            "status": "submitted",
            "created_at": datetime.now().isoformat(),
        })

        # Schedule execution
        background_tasks.add_task(
            execute_task_in_container,
            agent_id,
            task_id,
            container,
        )

        logger.info("task_scheduled", agent_id=agent_id, task_id=task_id)

        return {
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "submitted",
            "created_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("task_submission_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@app.get("/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """Get current status of an agent."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]

    try:
        container = docker_client.containers.get(agent["container_id"])
        container.reload()

        stats = container.stats(stream=False)
        memory_usage_mb = stats["memory_stats"]["usage"] / (1024 * 1024)

        return {
            "agent_id": agent_id,
            "name": agent["name"],
            "status": agent["status"],
            "container_status": container.status,
            "created_at": agent["created_at"],
            "tasks": agent["tasks"],
            "memory_usage_mb": round(memory_usage_mb, 2),
        }

    except Exception as e:
        logger.error("status_check_failed", error=str(e))
        return {
            "agent_id": agent_id,
            "error": str(e),
            "tasks": agent.get("tasks", []),
        }


@app.get("/agents/{agent_id}/logs")
async def stream_logs(agent_id: str):
    """Stream agent container logs in real-time."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]

    try:
        container = docker_client.containers.get(agent["container_id"])

        async def log_generator():
            try:
                for log in container.logs(stream=True, follow=True):
                    yield f"data: {log.decode('utf-8')}\n\n"
            except Exception as e:
                yield f"data: Error streaming logs: {str(e)}\n\n"

        return StreamingResponse(log_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error("log_stream_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to stream logs: {str(e)}")


@app.delete("/agents/{agent_id}")
async def terminate_agent(agent_id: str):
    """
    Terminate and clean up an agent instance.

    Stops the container, removes volumes, and deletes agent record.
    """
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]

    logger.info("terminating_agent", agent_id=agent_id)

    try:
        # Stop and remove container
        container = docker_client.containers.get(agent["container_id"])
        container.stop(timeout=10)
        container.remove(force=True)

        logger.info("container_removed", agent_id=agent_id)

        # Remove volumes
        for vol_name in agent["volumes"].values():
            try:
                volume = docker_client.volumes.get(vol_name)
                volume.remove()
                logger.info("volume_removed", agent_id=agent_id, volume=vol_name)
            except Exception as e:
                logger.warning("volume_removal_failed", volume=vol_name, error=str(e))

        # Remove from registry
        del agents[agent_id]

        logger.info("agent_terminated", agent_id=agent_id)

        return {
            "status": "terminated",
            "agent_id": agent_id,
            "terminated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("termination_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to terminate agent: {str(e)}")


@app.get("/agents")
async def list_agents():
    """List all active agents."""
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


@app.get("/")
async def root():
    """Root endpoint - redirects to API docs."""
    return {
        "message": "Claude Managed Agents API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "agents": "/agents",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
