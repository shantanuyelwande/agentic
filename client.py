#!/usr/bin/env python3
"""
Client for Claude Managed Agents API v2.0

Submit tasks via HTTP API and poll for results.

Usage:
    python client.py "your task here"
    python client.py "Extract emails from: john@example.com"
"""

import asyncio
import json
import sys
import os
import httpx
from typing import Optional
from datetime import datetime

BASE_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")
HTTP_TIMEOUT = 30.0


async def health_check(client: httpx.AsyncClient) -> bool:
    """Check if API is healthy."""
    try:
        response = await client.get("/health", timeout=HTTP_TIMEOUT)
        return response.status_code == 200
    except Exception:
        return False


async def list_skills(client: httpx.AsyncClient) -> None:
    """List available skills."""
    print("\n📚 Available Skills:")
    print("-" * 60)

    try:
        response = await client.get("/skills", timeout=HTTP_TIMEOUT)
        if response.status_code != 200:
            print("   ❌ Error fetching skills")
            return

        data = response.json()
        skills = data.get("skills", [])

        if not skills:
            print("   (none)")
            return

        for skill in skills:
            print(f"   • {skill['name']}")
            print(f"     {skill['description']}")
            print()

    except Exception as e:
        print(f"   ⚠️  Error: {e}")


async def submit_task(
    client: httpx.AsyncClient,
    task: str,
    max_steps: int = 10,
    timeout: int = 300,
) -> Optional[str]:
    """Submit a task to the API."""
    print(f"\n📝 Submitting task...")
    print(f"   Input: {task[:80]}{'...' if len(task) > 80 else ''}")
    print(f"   Max steps: {max_steps}, Timeout: {timeout}s")

    try:
        response = await client.post(
            "/tasks",
            json={
                "input": task,
                "max_steps": max_steps,
                "timeout": timeout,
            },
            timeout=HTTP_TIMEOUT,
        )

        if response.status_code != 200:
            print(f"   ❌ Error: {response.text}")
            return None

        data = response.json()
        task_id = data.get("task_id")
        print(f"   ✅ Submitted: {task_id[:12]}...")

        return task_id

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


async def poll_task(
    client: httpx.AsyncClient,
    task_id: str,
    poll_interval: float = 1.0,
    max_wait: int = 300,
) -> bool:
    """Poll task until completion."""
    print(f"\n⏳ Polling task status (max {max_wait}s)...")

    start_time = datetime.now()

    for i in range(max_wait // int(poll_interval)):
        try:
            response = await client.get(f"/tasks/{task_id}", timeout=HTTP_TIMEOUT)

            if response.status_code != 200:
                print(f"   ❌ Error checking status: {response.text}")
                return False

            data = response.json()
            status = data.get("status")

            elapsed = int((datetime.now() - start_time).total_seconds())

            if status == "completed":
                steps = data.get("steps_taken", 0)
                duration = data.get("duration_seconds", 0)
                print(f"   ✅ Completed in {elapsed}s ({steps} steps, {duration:.1f}s execution)")
                return True

            elif status == "failed":
                error = data.get("error", "Unknown error")
                print(f"   ❌ Failed: {error}")
                return False

            elif status == "timeout":
                error = data.get("error", "Task timeout")
                print(f"   ⏱️  {error}")
                return False

            elif status == "queued":
                print(f"   ⏳ Queued... ({elapsed}s)")
            elif status == "running":
                steps = data.get("steps_taken", 0)
                print(f"   🔄 Running... ({elapsed}s, {steps} steps)")

            await asyncio.sleep(poll_interval)

        except asyncio.TimeoutError:
            print(f"   ❌ Request timeout")
            return False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

    print(f"   ⏱️  Timeout after {max_wait}s")
    return False


async def get_result(client: httpx.AsyncClient, task_id: str) -> Optional[dict]:
    """Get full task result."""
    print(f"\n📊 Task Result:")
    print("-" * 60)

    try:
        response = await client.get(f"/tasks/{task_id}", timeout=HTTP_TIMEOUT)

        if response.status_code != 200:
            print(f"❌ Error: {response.text}")
            return None

        data = response.json()

        # Display summary
        print(f"Task ID:      {data.get('task_id', 'N/A')[:12]}...")
        print(f"Status:       {data.get('status', 'unknown').upper()}")
        print(f"Steps:        {data.get('steps_taken', 0)}")
        print(f"Duration:     {data.get('duration_seconds', 0):.1f}s")

        if data.get("error"):
            print(f"Error:        {data.get('error')}")

        # Display result if available
        if data.get("result"):
            print(f"\nResult:")
            print("-" * 60)
            result_text = data.get("result", "")
            if len(result_text) > 500:
                print(result_text[:500])
                print(f"\n... (truncated, {len(result_text)} total chars)")
            else:
                print(result_text)

        return data

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def main():
    """Main workflow."""
    print("=" * 70)
    print("Claude Managed Agents - Client v2.0")
    print("=" * 70)

    # Get task from command line
    if len(sys.argv) < 2:
        print("\nUsage: python client.py 'your task here'")
        print("\nExamples:")
        print("  python client.py 'Extract emails from: john@example.com'")
        print("  python client.py 'Analyze this data'")
        return

    task = " ".join(sys.argv[1:])

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Check API health
        print(f"\n🔗 Connecting to {BASE_URL}...")
        healthy = await health_check(client)

        if not healthy:
            print("❌ API is not responding. Make sure it's running:")
            print("   docker-compose up")
            return

        print("✅ API is healthy")

        # List skills
        await list_skills(client)

        # Submit task
        task_id = await submit_task(client, task)
        if not task_id:
            return

        # Poll until completion
        completed = await poll_task(client, task_id, poll_interval=1.0, max_wait=300)

        # Get result
        if completed or True:  # Always show result
            await get_result(client, task_id)

        print("\n" + "=" * 70)
        if completed:
            print("✅ Task completed successfully!")
        else:
            print("⚠️  Task did not complete")
        print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
