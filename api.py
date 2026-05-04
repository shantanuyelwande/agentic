"""
API Service for Claude Managed Agents

Lightweight FastAPI service that:
- Accepts task submissions
- Stores task metadata in Redis
- Queues tasks for worker processing
- Provides task status polling
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis
import structlog

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
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TASK_TTL_SECONDS = int(os.getenv("TASK_TTL_SECONDS", 86400))  # 24 hours default

# Redis client
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("redis_connected", url=REDIS_URL)
except Exception as e:
    logger.error("redis_connection_failed", error=str(e))
    redis_client = None

# FastAPI app
app = FastAPI(
    title="Claude Managed Agents API",
    description="API for submitting and monitoring Claude agent tasks",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Pydantic Models
class TaskSubmissionRequest(BaseModel):
    """Request to submit a task."""
    input: str = Field(..., description="Task description for Claude")
    max_steps: int = Field(10, description="Max agent iterations", ge=1, le=100)
    timeout: int = Field(300, description="Task timeout in seconds", ge=10, le=3600)


class TaskResponse(BaseModel):
    """Task information response."""
    task_id: str
    status: str  # queued, running, completed, failed, timeout
    input: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    steps_taken: Optional[int] = None
    duration_seconds: Optional[float] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class SkillInfo(BaseModel):
    """Skill metadata."""
    name: str
    description: str


class QueueDepth(BaseModel):
    """Queue status."""
    queued: int
    running: int


# Helper Functions
def get_redis() -> redis.Redis:
    """Get Redis client, raise if not available."""
    if not redis_client:
        raise HTTPException(
            status_code=503,
            detail="Redis is not available"
        )
    return redis_client


def load_skills_metadata() -> list[Dict[str, str]]:
    """Load skills metadata from filesystem."""
    skills = []
    skills_dir = "/app/.claude/skills"

    if not os.path.exists(skills_dir):
        return skills

    try:
        for skill_name in os.listdir(skills_dir):
            skill_path = os.path.join(skills_dir, skill_name)
            if not os.path.isdir(skill_path):
                continue

            skill_md = os.path.join(skill_path, "SKILL.md")
            if os.path.exists(skill_md):
                try:
                    # Parse frontmatter to get name and description
                    with open(skill_md, 'r') as f:
                        content = f.read()

                    # Extract YAML frontmatter
                    if content.startswith("---"):
                        _, frontmatter, _ = content.split("---", 2)
                        # Simple YAML parsing for name and description
                        import yaml
                        metadata = yaml.safe_load(frontmatter)
                        if metadata and 'name' in metadata and 'description' in metadata:
                            skills.append({
                                'name': metadata['name'],
                                'description': metadata['description']
                            })
                except Exception as e:
                    logger.warning("error_parsing_skill", skill=skill_name, error=str(e))
    except Exception as e:
        logger.warning("error_loading_skills", error=str(e))

    return skills


# API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    redis_ok = False
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis_available": redis_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/info")
async def get_info():
    """Get API configuration info."""
    return {
        "version": "2.0.0",
        "redis_url": REDIS_URL,
        "task_ttl_seconds": TASK_TTL_SECONDS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/skills")
async def list_skills():
    """List available skills (metadata only)."""
    skills = load_skills_metadata()
    return {
        "count": len(skills),
        "skills": skills
    }


@app.post("/tasks")
async def submit_task(request: TaskSubmissionRequest) -> Dict[str, Any]:
    """
    Submit a task for execution.

    Returns task_id for polling status.
    """
    redis = get_redis()

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    logger.info("task_submitted", task_id=task_id, input_preview=request.input[:50])

    try:
        # Store task metadata in Redis
        task_key = f"task:{task_id}"
        task_data = {
            "task_id": task_id,
            "input": request.input,
            "max_steps": request.max_steps,
            "timeout": request.timeout,
            "status": "queued",
            "created_at": now,
            "steps_taken": 0,
        }

        redis.hset(task_key, mapping=task_data)
        redis.expire(task_key, TASK_TTL_SECONDS)

        # Push to queue
        queue_item = json.dumps(task_data)
        redis.rpush("task_queue", queue_item)

        logger.info("task_queued", task_id=task_id)

        return {
            "task_id": task_id,
            "status": "queued",
            "created_at": now,
        }

    except Exception as e:
        logger.error("task_submission_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> TaskResponse:
    """Get task status and results."""
    redis = get_redis()

    try:
        task_key = f"task:{task_id}"
        task_data = redis.hgetall(task_key)

        if not task_data:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Use result from task hash (stored as plain text)
        result = task_data.get("result")

        # Parse numeric fields
        steps_taken = None
        if task_data.get("steps_taken"):
            try:
                steps_taken = int(task_data["steps_taken"])
            except (ValueError, TypeError):
                pass

        duration_seconds = None
        if task_data.get("duration_seconds"):
            try:
                duration_seconds = float(task_data["duration_seconds"])
            except (ValueError, TypeError):
                pass

        return TaskResponse(
            task_id=task_id,
            status=task_data.get("status", "unknown"),
            input=task_data.get("input"),
            result=result,
            error=task_data.get("error"),
            steps_taken=steps_taken,
            duration_seconds=duration_seconds,
            created_at=task_data.get("created_at", ""),
            started_at=task_data.get("started_at"),
            completed_at=task_data.get("completed_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("task_status_error", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@app.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500)
) -> Dict[str, Any]:
    """List all tasks, optionally filtered by status."""
    redis = get_redis()

    try:
        # Get all task keys
        task_keys = redis.keys("task:*")
        tasks = []

        for key in task_keys[:limit]:
            task_data = redis.hgetall(key)
            if task_data:
                if status is None or task_data.get("status") == status:
                    tasks.append({
                        "task_id": task_data.get("task_id"),
                        "status": task_data.get("status"),
                        "created_at": task_data.get("created_at"),
                        "input_preview": task_data.get("input", "")[:50],
                    })

        return {
            "count": len(tasks),
            "limit": limit,
            "tasks": tasks
        }

    except Exception as e:
        logger.error("list_tasks_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")


@app.get("/queue/depth")
async def get_queue_depth() -> QueueDepth:
    """Get queue status."""
    redis = get_redis()

    try:
        queued = redis.llen("task_queue")
        running = len(redis.keys("task_running:*"))

        return QueueDepth(
            queued=queued,
            running=running
        )

    except Exception as e:
        logger.error("queue_depth_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get queue depth: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Claude Managed Agents API v2.0",
        "docs": "/docs",
        "health": "/health",
        "skills": "/skills",
        "tasks": "/tasks",
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
