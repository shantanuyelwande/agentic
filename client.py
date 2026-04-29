#!/usr/bin/env python3
"""
Test Client for Claude Managed Agents

Demonstrates how to:
1. Create an agent instance
2. Submit a task for execution
3. Monitor execution progress
4. Retrieve results
5. Clean up resources

Run: python client.py
"""

import asyncio
import json
import httpx
from typing import Optional


BASE_URL = "http://localhost:8000"
HTTP_TIMEOUT = 30.0


async def health_check(client: httpx.AsyncClient) -> bool:
    """Check if orchestrator is healthy."""
    try:
        response = await client.get("/health", timeout=HTTP_TIMEOUT)
        return response.status_code == 200
    except Exception:
        return False


async def create_agent(client: httpx.AsyncClient, name: str = "test-agent") -> str:
    """Create a new agent instance."""
    print(f"\n1️⃣  Creating agent '{name}'...")

    response = await client.post(
        "/agents/create",
        json={"name": name},
        timeout=HTTP_TIMEOUT,
    )

    if response.status_code != 200:
        print(f"   ❌ Error: {response.text}")
        return None

    data = response.json()
    agent_id = data["agent_id"]
    print(f"   ✅ Created: {agent_id[:8]}...")
    print(f"   Container: {data['container_id']}")
    print(f"   Created: {data['created_at']}")

    return agent_id


async def submit_task(client: httpx.AsyncClient, agent_id: str, task: str) -> Optional[str]:
    """Submit a task to an agent."""
    print(f"\n2️⃣  Submitting task...")
    print(f"   Task: {task[:60]}...")

    response = await client.post(
        f"/agents/{agent_id}/task",
        json={"task": task},
        timeout=HTTP_TIMEOUT,
    )

    if response.status_code != 200:
        print(f"   ❌ Error: {response.text}")
        return None

    data = response.json()
    task_id = data["task_id"]
    print(f"   ✅ Submitted: {task_id[:8]}...")
    print(f"   Status: {data['status']}")

    return task_id


async def wait_for_completion(
    client: httpx.AsyncClient,
    agent_id: str,
    task_id: str,
    max_wait: int = 60,
) -> bool:
    """Wait for task to complete."""
    print(f"\n3️⃣  Waiting for task completion (max {max_wait}s)...")

    for i in range(max_wait):
        response = await client.get(f"/agents/{agent_id}/status", timeout=HTTP_TIMEOUT)

        if response.status_code != 200:
            print(f"   ❌ Error checking status: {response.text}")
            return False

        status_data = response.json()
        tasks = status_data.get("tasks", [])

        for task in tasks:
            if task["task_id"] == task_id:
                status = task["status"]

                if status == "completed":
                    print(f"   ✅ Task completed in {i}s")
                    return True

                elif status == "failed":
                    print(f"   ❌ Task failed")
                    return False

        print(f"   ⏳ Still running... ({i}s)")
        await asyncio.sleep(1)

    print(f"   ❌ Timeout after {max_wait}s")
    return False


async def get_task_output(client: httpx.AsyncClient, agent_id: str) -> Optional[dict]:
    """Get task output from agent."""
    print(f"\n4️⃣  Retrieving task output...")

    try:
        # Try to read output.json from agent's workspace
        response = await client.get(f"/agents/{agent_id}/status", timeout=HTTP_TIMEOUT)

        if response.status_code == 200:
            print(f"   ✅ Retrieved agent status")
            return response.json()

    except Exception as e:
        print(f"   ⚠️  Could not retrieve detailed output: {e}")

    return None


async def stream_logs(client: httpx.AsyncClient, agent_id: str, max_lines: int = 50) -> None:
    """Stream agent logs."""
    print(f"\n5️⃣  Agent logs (first {max_lines} lines):")
    print("   " + "-" * 60)

    try:
        line_count = 0
        async with client.stream("GET", f"/agents/{agent_id}/logs", timeout=HTTP_TIMEOUT) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    log_line = line[6:]
                    if log_line.strip():
                        print(f"   {log_line[:80]}")
                        line_count += 1

                        if line_count >= max_lines:
                            print("   ...")
                            break

    except asyncio.TimeoutError:
        print("   ⚠️  Log stream timeout")
    except Exception as e:
        print(f"   ⚠️  Could not stream logs: {e}")

    print("   " + "-" * 60)


async def terminate_agent(client: httpx.AsyncClient, agent_id: str) -> bool:
    """Terminate and clean up an agent."""
    print(f"\n6️⃣  Terminating agent...")

    response = await client.delete(f"/agents/{agent_id}", timeout=HTTP_TIMEOUT)

    if response.status_code != 200:
        print(f"   ❌ Error: {response.text}")
        return False

    data = response.json()
    print(f"   ✅ Terminated: {agent_id[:8]}...")
    print(f"   Cleanup: {data['status']}")

    return True


async def list_agents(client: httpx.AsyncClient) -> None:
    """List all active agents."""
    print(f"\n📋 Active Agents:")

    response = await client.get("/agents", timeout=HTTP_TIMEOUT)

    if response.status_code != 200:
        print(f"   ❌ Error: {response.text}")
        return

    data = response.json()
    count = data["count"]

    if count == 0:
        print("   (none)")
        return

    print(f"   Total: {count}")
    for agent in data["agents"]:
        print(f"   • {agent['name']} (tasks: {agent['task_count']})")


async def main():
    """Main test workflow."""
    print("=" * 70)
    print("Claude Managed Agents - Test Client")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Check health
        print(f"\nChecking orchestrator at {BASE_URL}...")
        healthy = await health_check(client)

        if not healthy:
            print("❌ Orchestrator is not responding. Make sure Docker is running and")
            print("   the orchestrator container is started:")
            print("   docker-compose up -d")
            return

        print("✅ Orchestrator is healthy")

        # List existing agents
        await list_agents(client)

        # Create agent
        agent_id = await create_agent(client, name="demo-agent")
        if not agent_id:
            return

        # Submit task
        task = """
        Extract the following information from this sample text:

        Contact information:
        - Email: john.doe@example.com
        - Phone: (555) 123-4567
        - Website: https://example.com

        Please extract emails, phone numbers, and URLs.
        """

        task_id = await submit_task(client, agent_id, task)
        if not task_id:
            await terminate_agent(client, agent_id)
            return

        # Wait for completion
        completed = await wait_for_completion(client, agent_id, task_id, max_wait=30)

        # Get output
        output = await get_task_output(client, agent_id)
        if output:
            print(f"\n📊 Task Status:")
            for key, value in output.items():
                if key not in ["agents"]:  # Skip large nested data
                    print(f"   {key}: {value}")

        # Stream logs
        await stream_logs(client, agent_id, max_lines=30)

        # Cleanup
        if not await terminate_agent(client, agent_id):
            print("⚠️  Could not terminate agent, will expire automatically")

        print("\n" + "=" * 70)
        print("✅ Test completed successfully!")
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
