#!/usr/bin/env python3
"""
Test Client for LangGraph Deep Agents

Demonstrates:
1. Create an isolated agent container
2. Submit a task (Plan-and-Execute via LangGraph)
3. Poll for completion
4. Retrieve results
5. Stream logs
6. Terminate and clean up

Run: python client.py
"""

import asyncio
import json
from typing import Optional

import httpx

BASE_URL = "http://localhost:8000"
HTTP_TIMEOUT = 30.0


async def health_check(client: httpx.AsyncClient) -> bool:
    try:
        resp = await client.get("/health", timeout=HTTP_TIMEOUT)
        return resp.status_code == 200
    except Exception:
        return False


async def create_agent(client: httpx.AsyncClient, name: str = "lg-agent") -> Optional[str]:
    print(f"\n1. Creating agent '{name}'...")
    resp = await client.post("/agents/create", json={"name": name}, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        print(f"   ERROR: {resp.text}")
        return None
    data = resp.json()
    print(f"   Created:   {data['agent_id'][:8]}...")
    print(f"   Container: {data['container_id']}")
    return data["agent_id"]


async def submit_task(client: httpx.AsyncClient, agent_id: str, task: str) -> Optional[str]:
    print(f"\n2. Submitting task...")
    print(f"   {task[:80]}...")
    resp = await client.post(
        f"/agents/{agent_id}/task",
        json={"task": task},
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        print(f"   ERROR: {resp.text}")
        return None
    data = resp.json()
    print(f"   Task ID: {data['task_id'][:8]}...")
    print(f"   Status:  {data['status']}")
    return data["task_id"]


async def wait_for_completion(
    client: httpx.AsyncClient,
    agent_id: str,
    task_id: str,
    max_wait: int = 120,
) -> bool:
    print(f"\n3. Waiting for completion (max {max_wait}s)...")
    for elapsed in range(max_wait):
        resp = await client.get(f"/agents/{agent_id}/status", timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            print(f"   ERROR checking status: {resp.text}")
            return False

        for task in resp.json().get("tasks", []):
            if task["task_id"] == task_id:
                if task["status"] == "completed":
                    print(f"   Completed in {elapsed}s")
                    return True
                if task["status"] == "failed":
                    print(f"   FAILED after {elapsed}s")
                    return False

        if elapsed % 10 == 0:
            print(f"   Running... ({elapsed}s)")
        await asyncio.sleep(1)

    print(f"   Timed out after {max_wait}s")
    return False


async def get_output(client: httpx.AsyncClient, agent_id: str) -> Optional[dict]:
    print(f"\n4. Retrieving output...")
    resp = await client.get(f"/agents/{agent_id}/status", timeout=HTTP_TIMEOUT)
    if resp.status_code == 200:
        print("   Retrieved agent status.")
        return resp.json()
    return None


async def stream_logs(client: httpx.AsyncClient, agent_id: str, max_lines: int = 40) -> None:
    print(f"\n5. Container logs (first {max_lines} lines):")
    print("   " + "-" * 60)
    try:
        count = 0
        async with client.stream("GET", f"/agents/{agent_id}/logs", timeout=HTTP_TIMEOUT) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    log_line = line[6:].strip()
                    if log_line:
                        print(f"   {log_line[:100]}")
                        count += 1
                        if count >= max_lines:
                            print("   ...")
                            break
    except asyncio.TimeoutError:
        print("   Log stream timeout.")
    except Exception as e:
        print(f"   Could not stream logs: {e}")
    print("   " + "-" * 60)


async def terminate_agent(client: httpx.AsyncClient, agent_id: str) -> bool:
    print(f"\n6. Terminating agent {agent_id[:8]}...")
    resp = await client.delete(f"/agents/{agent_id}", timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        print(f"   ERROR: {resp.text}")
        return False
    print(f"   Terminated: {resp.json()['status']}")
    return True


async def list_agents(client: httpx.AsyncClient) -> None:
    print("\n--- Active Agents ---")
    resp = await client.get("/agents", timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        print(f"   ERROR: {resp.text}")
        return
    data = resp.json()
    if data["count"] == 0:
        print("   (none)")
    else:
        print(f"   Total: {data['count']}")
        for a in data["agents"]:
            print(f"   • {a['name']} — tasks: {a['task_count']}, status: {a['status']}")


async def main():
    print("=" * 70)
    print("LangGraph Deep Agents — Test Client")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        print(f"\nChecking orchestrator at {BASE_URL}...")
        if not await health_check(client):
            print("Orchestrator not responding. Start with:")
            print("  docker-compose up -d")
            return
        print("Orchestrator is healthy.")

        await list_agents(client)

        agent_id = await create_agent(client, name="demo-lg-agent")
        if not agent_id:
            return

        # Demo task: uses the Plan-and-Execute deep agent
        task = (
            "Research the key differences between LangChain's ReAct agents and "
            "Plan-and-Execute agents. Summarise: (1) how each works, (2) when to "
            "use each, and (3) their relative strengths and weaknesses. "
            "Cite at least 2 sources."
        )

        task_id = await submit_task(client, agent_id, task)
        if not task_id:
            await terminate_agent(client, agent_id)
            return

        completed = await wait_for_completion(client, agent_id, task_id, max_wait=180)

        output = await get_output(client, agent_id)
        if output:
            print("\n--- Task Summary ---")
            for key, value in output.items():
                if key not in ("agents",):
                    print(f"  {key}: {value}")

        await stream_logs(client, agent_id, max_lines=30)

        if not await terminate_agent(client, agent_id):
            print("Could not terminate agent — it will expire automatically.")

        print("\n" + "=" * 70)
        print("Test complete." if completed else "Test finished with errors.")
        print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        import traceback
        print(f"\nError: {e}")
        traceback.print_exc()
