"""
LangGraph Agent Orchestrator

Manages LangGraph agent instances, job queuing, and results persistence.
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

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "langchain-agent:latest")
AGENTS_DIR = Path("/data/agents")
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

try:
    docker_client = docker.from_env()
    docker_client.ping()
    logger.info("docker_connected")
except Exception as e:
    logger.error("docker_connection_failed", error=str(e))
    docker_client = None

app = FastAPI(
    title="LangGraph Deep Agents",
    description="Containerised LangGraph Plan-and-Execute agents powered by Claude",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

agents: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateAgentRequest(BaseModel):
    name: Optional[str] = Field(None, description="Human-readable agent name")
    config: Optional[Dict[str, Any]] = Field(None, description="Optional agent config")


class TaskRequest(BaseModel):
    task: str = Field(..., description="Task description for the LangGraph agent")
    timeout: int = Field(300, description="Timeout in seconds", ge=10, le=3600)


class AgentInfo(BaseModel):
    agent_id: str
    name: str
    status: str
    created_at: str
    task_count: int


class TaskResult(BaseModel):
    task_id: str
    agent_id: str
    status: str
    output: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_docker_client():
    if not docker_client:
        raise HTTPException(
            status_code=500,
            detail="Docker is not available. Ensure the Docker daemon is running.",
        )
    return docker_client


def write_task_to_container(container, task_data: Dict[str, Any]) -> None:
    try:
        import tarfile
        import io

        task_json = json.dumps(task_data, indent=2).encode()
        info = tarfile.TarInfo(name="task.json")
        info.size = len(task_json)

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            tar.addfile(tarinfo=info, fileobj=io.BytesIO(task_json))
        buf.seek(0)

        container.put_archive("/workspace", buf.getvalue())
        logger.info("task_written_to_container", task_id=task_data.get("task_id"))

    except Exception as e:
        logger.error("error_writing_task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to write task to container: {e}")


async def execute_task_in_container(
    agent_id: str,
    task_id: str,
    container,
) -> None:
    logger.info("executing_task_in_background", agent_id=agent_id, task_id=task_id)
    try:
        exit_code, _ = container.exec_run(
            "python /app/langgraph_agent.py",
            stdout=True,
            stderr=True,
            demux=False,
        )
        logger.info("task_executed", agent_id=agent_id, task_id=task_id, exit_code=exit_code)

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "docker_available": docker_client is not None,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/agents/create", response_model=Dict[str, Any])
async def create_agent(request: CreateAgentRequest):
    """Create a new isolated LangGraph agent container."""
    client = get_docker_client()
    agent_id = str(uuid.uuid4())
    logger.info("creating_agent", agent_id=agent_id)

    try:
        ws_volume = client.volumes.create(name=f"agent-{agent_id}-ws")
        mem_volume = client.volumes.create(name=f"agent-{agent_id}-mem")

        container = client.containers.run(
            DOCKER_IMAGE,
            detach=True,
            name=f"agent-{agent_id[:8]}",
            environment={
                "AGENT_ID": agent_id,
                "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
                "CLAUDE_MODEL": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
            },
            volumes={
                ws_volume.name: {"bind": "/workspace", "mode": "rw"},
                mem_volume.name: {"bind": "/memory", "mode": "rw"},
            },
            mem_limit="2g",
            cpu_quota=100000,
            cpu_period=100000,
            healthcheck={
                "test": ["CMD", "python", "-c", "import langgraph; import sys; sys.exit(0)"],
                "interval": 30_000_000_000,
                "timeout": 10_000_000_000,
                "retries": 3,
            },
        )

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
            },
        }

        logger.info("agent_created", agent_id=agent_id, container_id=container.id[:12])

        return {
            "agent_id": agent_id,
            "name": agents[agent_id]["name"],
            "status": "created",
            "container_id": container.id[:12],
            "created_at": agents[agent_id]["created_at"],
        }

    except Exception as e:
        logger.error("agent_creation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {e}")


@app.post("/agents/{agent_id}/task", response_model=Dict[str, Any])
async def submit_task(agent_id: str, request: TaskRequest, background_tasks: BackgroundTasks):
    """Submit a task to a LangGraph agent for background execution."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]
    task_id = str(uuid.uuid4())
    logger.info("submitting_task", agent_id=agent_id, task_id=task_id)

    try:
        container = docker_client.containers.get(agent["container_id"])
        write_task_to_container(container, {
            "task_id": task_id,
            "task": request.task,
            "timeout": request.timeout,
        })

        agents[agent_id]["tasks"].append({
            "task_id": task_id,
            "status": "submitted",
            "created_at": datetime.now().isoformat(),
        })

        background_tasks.add_task(execute_task_in_container, agent_id, task_id, container)

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
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {e}")


@app.get("/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """Get current status and task list for an agent."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]
    try:
        container = docker_client.containers.get(agent["container_id"])
        container.reload()
        stats = container.stats(stream=False)
        memory_mb = stats["memory_stats"].get("usage", 0) / (1024 * 1024)

        return {
            "agent_id": agent_id,
            "name": agent["name"],
            "status": agent["status"],
            "container_status": container.status,
            "created_at": agent["created_at"],
            "tasks": agent["tasks"],
            "memory_usage_mb": round(memory_mb, 2),
        }

    except Exception as e:
        logger.error("status_check_failed", error=str(e))
        return {"agent_id": agent_id, "error": str(e), "tasks": agent.get("tasks", [])}


@app.get("/agents/{agent_id}/logs")
async def stream_logs(agent_id: str):
    """Stream container logs in real-time (Server-Sent Events)."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    container = docker_client.containers.get(agents[agent_id]["container_id"])

    async def log_gen():
        try:
            for log in container.logs(stream=True, follow=True):
                yield f"data: {log.decode('utf-8')}\n\n"
        except Exception as e:
            yield f"data: Error: {e}\n\n"

    return StreamingResponse(log_gen(), media_type="text/event-stream")


@app.delete("/agents/{agent_id}")
async def terminate_agent(agent_id: str):
    """Stop the container and remove all volumes for an agent."""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent = agents[agent_id]
    logger.info("terminating_agent", agent_id=agent_id)

    try:
        container = docker_client.containers.get(agent["container_id"])
        container.stop(timeout=10)
        container.remove(force=True)

        for vol_name in agent["volumes"].values():
            try:
                docker_client.volumes.get(vol_name).remove()
            except Exception as e:
                logger.warning("volume_removal_failed", volume=vol_name, error=str(e))

        del agents[agent_id]

        return {
            "status": "terminated",
            "agent_id": agent_id,
            "terminated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("termination_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to terminate agent: {e}")


@app.get("/agents")
async def list_agents():
    """List all active agents."""
    return {
        "count": len(agents),
        "agents": [
            {
                "id": a["id"],
                "name": a["name"],
                "status": a["status"],
                "created_at": a["created_at"],
                "task_count": len(a["tasks"]),
            }
            for a in agents.values()
        ],
    }


@app.get("/")
async def root():
    return {
        "message": "LangGraph Deep Agents API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "agents": "/agents",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")
