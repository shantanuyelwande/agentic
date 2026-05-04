"""
Worker Service for Claude Managed Agents

Polls Redis queue and executes tasks using the Claude Agent SDK.
- Receives tasks from task_queue
- Executes using agent_instance.run_agent()
- Updates task status in Redis
- Handles timeouts and errors gracefully
"""

import asyncio
import json
import os
import sys
import socket
from datetime import datetime, timezone
from typing import Dict, Any

import redis
import structlog

from agent_instance import run_agent

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
CHECKPOINT_INTERVAL = int(os.getenv("CHECKPOINT_INTERVAL", 3))
WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())
QUEUE_POLL_TIMEOUT = 1  # seconds

# Redis client
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("redis_connected", worker_id=WORKER_ID, url=REDIS_URL)
except Exception as e:
    logger.error("redis_connection_failed", error=str(e))
    redis_client = None


def get_redis() -> redis.Redis:
    """Get Redis client with connection pooling."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            redis_client.ping()
        except Exception as e:
            logger.error("redis_reconnect_failed", error=str(e))
    return redis_client


def update_task_status(
    task_id: str,
    status: str,
    **kwargs
) -> None:
    """Update task status in Redis."""
    try:
        redis = get_redis()
        task_key = f"task:{task_id}"

        # Build update dict
        update_data = {"status": status}
        update_data.update(kwargs)

        # Update task hash
        redis.hset(task_key, mapping=update_data)

        logger.info(
            "task_status_updated",
            task_id=task_id,
            status=status,
            **kwargs
        )
    except Exception as e:
        logger.error("error_updating_task_status", task_id=task_id, error=str(e))


def save_checkpoint(task_id: str, progress: Dict[str, Any]) -> None:
    """Save task checkpoint to Redis."""
    try:
        redis = get_redis()
        checkpoint_key = f"checkpoint:{task_id}"
        redis.setex(
            checkpoint_key,
            3600,  # 1 hour TTL
            json.dumps(progress)
        )
        logger.debug("checkpoint_saved", task_id=task_id)
    except Exception as e:
        logger.warning("error_saving_checkpoint", task_id=task_id, error=str(e))


def clear_checkpoint(task_id: str) -> None:
    """Clear task checkpoint."""
    try:
        redis = get_redis()
        checkpoint_key = f"checkpoint:{task_id}"
        redis.delete(checkpoint_key)
    except Exception as e:
        logger.warning("error_clearing_checkpoint", task_id=task_id, error=str(e))


def store_result(task_id: str, result: Any) -> None:
    """Store task result in Redis."""
    try:
        redis = get_redis()
        result_key = f"task_result:{task_id}"
        redis.setex(
            result_key,
            86400,  # 24 hours TTL
            json.dumps(result, default=str)
        )
    except Exception as e:
        logger.error("error_storing_result", task_id=task_id, error=str(e))


async def execute_task(task_data: Dict[str, Any]) -> None:
    """
    Execute a single task.

    1. Update status to running
    2. Call agent
    3. Update status with result
    4. Store result in Redis
    """
    task_id = task_data.get("task_id")
    timeout = task_data.get("timeout", 300)

    logger.info(
        "executing_task",
        task_id=task_id,
        input_preview=task_data.get("input", "")[:50],
        timeout=timeout,
    )

    started_at = datetime.now(timezone.utc).isoformat()
    update_task_status(task_id, "running", started_at=started_at)

    try:
        # Run agent with timeout
        result = await asyncio.wait_for(
            run_agent(task_data),
            timeout=timeout
        )

        completed_at = datetime.now(timezone.utc).isoformat()

        # Update task status with result
        update_task_status(
            task_id,
            "completed",
            result=result.get("result", ""),
            steps_taken=result.get("steps_taken", 0),
            duration_seconds=result.get("duration_seconds", 0),
            completed_at=completed_at,
        )

        # Store full result
        store_result(task_id, result)

        # Clear checkpoint on success
        clear_checkpoint(task_id)

        logger.info(
            "task_completed",
            task_id=task_id,
            steps=result.get("steps_taken"),
            duration=result.get("duration_seconds"),
        )

    except asyncio.TimeoutError:
        logger.warning("task_timeout", task_id=task_id, timeout=timeout)
        completed_at = datetime.now(timezone.utc).isoformat()
        update_task_status(
            task_id,
            "timeout",
            error=f"Task exceeded timeout of {timeout}s",
            completed_at=completed_at,
        )
        store_result(task_id, {
            "status": "timeout",
            "error": f"Task exceeded timeout of {timeout}s",
        })

    except Exception as e:
        logger.error("task_execution_error", task_id=task_id, error=str(e))
        completed_at = datetime.now(timezone.utc).isoformat()
        update_task_status(
            task_id,
            "failed",
            error=str(e),
            completed_at=completed_at,
        )
        store_result(task_id, {
            "status": "failed",
            "error": str(e),
        })

    finally:
        # Always clear checkpoint
        clear_checkpoint(task_id)


async def poll_queue() -> None:
    """
    Main worker loop.

    Continuously poll Redis queue for tasks and execute them.
    """
    logger.info("worker_starting", worker_id=WORKER_ID)

    if redis_client is None:
        logger.error("redis_unavailable_at_startup")
        sys.exit(1)

    retry_count = 0
    max_retries = 5

    while True:
        try:
            redis = get_redis()

            # Block until task available (timeout=1 to allow graceful shutdown)
            queue_item = redis.blpop("task_queue", timeout=QUEUE_POLL_TIMEOUT)

            if queue_item:
                _, task_json = queue_item
                try:
                    task_data = json.loads(task_json)
                    task_id = task_data.get("task_id")

                    logger.info(
                        "task_dequeued",
                        task_id=task_id,
                        worker_id=WORKER_ID
                    )

                    # Execute task
                    await execute_task(task_data)

                    # Reset retry count on success
                    retry_count = 0

                except json.JSONDecodeError as e:
                    logger.error("invalid_task_json", error=str(e))
                    retry_count = 0  # Don't retry malformed JSON
                except Exception as e:
                    logger.error("error_executing_task", error=str(e))
                    retry_count = 0

            else:
                # No task available, continue polling
                retry_count = 0

        except redis.ConnectionError as e:
            retry_count += 1
            logger.warning(
                "redis_connection_error",
                retry_count=retry_count,
                max_retries=max_retries,
                error=str(e),
            )

            if retry_count > max_retries:
                logger.error("redis_unavailable_max_retries_exceeded")
                sys.exit(1)

            # Wait before retry
            await asyncio.sleep(2 ** retry_count)  # Exponential backoff

        except Exception as e:
            logger.error("worker_error", error=str(e))
            retry_count = 0
            await asyncio.sleep(1)


def main():
    """Entry point."""
    try:
        asyncio.run(poll_queue())
    except KeyboardInterrupt:
        logger.info("worker_interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error("worker_fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
