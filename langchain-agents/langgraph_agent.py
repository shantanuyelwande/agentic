"""
LangGraph Deep Agent

Plan-and-Execute agent using LangGraph + Claude via langchain-anthropic.
Reads task from /workspace/task.json, writes output to /workspace/output.json.

Architecture:
  planner -> agent (executor) -> replan -> [loop or END]
"""

import os
import json
import asyncio
import operator
from pathlib import Path
from datetime import datetime
from typing import TypedDict, List, Tuple, Optional, Annotated, Union

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from tools.langchain_tools import get_all_tools

AGENT_ID = os.getenv("AGENT_ID", "unknown")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
WORKSPACE = Path("/workspace")
MEMORY_DIR = Path("/memory")
SKILLS_DIR = Path("/app/.claude/skills")


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class PlanExecuteState(TypedDict):
    input: str
    plan: List[str]
    past_steps: Annotated[List[Tuple[str, str]], operator.add]
    response: Optional[str]


# ---------------------------------------------------------------------------
# Output schemas (structured output from LLM)
# ---------------------------------------------------------------------------

class Plan(BaseModel):
    """Ordered list of steps to complete the task."""
    steps: List[str] = Field(description="Concrete, actionable steps to execute in order")


class Response(BaseModel):
    """Final answer when the task is fully complete."""
    response: str = Field(description="Final response summarising completed work and results")


class Act(BaseModel):
    """Either a new/updated plan or a final response."""
    action: Union[Response, Plan] = Field(
        description="Respond with a Plan if more steps are needed, Response if the task is done"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_skills_context() -> str:
    if not SKILLS_DIR.exists():
        return ""
    parts = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            parts.append(f"\n## Skill: {skill_dir.name}\n{skill_file.read_text()}")
    return ("# Available Skills\n" + "\n".join(parts)) if parts else ""


def save_session(thread_id: str, data: dict) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent_id": AGENT_ID,
        "thread_id": thread_id,
        "updated_at": datetime.now().isoformat(),
        **data,
    }
    (MEMORY_DIR / "session.json").write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------

def build_app(llm: ChatAnthropic, tools: list, skills_context: str):
    """Compile the Plan-and-Execute LangGraph application."""

    system_prompt = f"""You are a deep reasoning AI agent with access to tools.
Complete tasks thoroughly and accurately.

{skills_context}

Guidelines:
- Use tools to gather real information; do not guess.
- Verify results before concluding.
- Provide structured, clear output.
"""

    # Executor: a ReAct sub-agent that handles individual steps
    executor_agent = create_react_agent(llm, tools, prompt=system_prompt)

    # Planner prompt
    planner_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            system_prompt
            + "\n\nCreate a concise step-by-step plan to complete the task. "
            "Each step must be a single, self-contained action.",
        ),
        ("human", "{objective}"),
    ])
    planner = planner_prompt | llm.with_structured_output(Plan)

    # Replanner prompt
    replanner_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            system_prompt
            + """

Original task: {input}

Original plan:
{plan}

Steps completed so far:
{past_steps}

Decide:
- If the task is fully complete, return a Response with a clear summary of all results.
- If more work is needed, return a Plan with only the remaining steps (do not repeat done steps).
""",
        ),
        ("human", "Is the task complete, or are more steps needed?"),
    ])
    replanner = replanner_prompt | llm.with_structured_output(Act)

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    async def plan_node(state: PlanExecuteState):
        plan = await planner.ainvoke({"objective": state["input"]})
        return {"plan": plan.steps}

    async def execute_node(state: PlanExecuteState):
        step = state["plan"][0]
        result = await executor_agent.ainvoke(
            {"messages": [HumanMessage(content=step)]}
        )
        last_msg = result["messages"][-1]
        return {
            "past_steps": [(step, last_msg.content)],
            "plan": state["plan"][1:],
        }

    async def replan_node(state: PlanExecuteState):
        past = "\n".join(
            f"Step: {s}\nResult: {r}" for s, r in state.get("past_steps", [])
        )
        output = await replanner.ainvoke(
            {
                "input": state["input"],
                "plan": "\n".join(f"- {s}" for s in state.get("plan", [])),
                "past_steps": past or "None yet.",
            }
        )
        if isinstance(output.action, Response):
            return {"response": output.action.response}
        return {"plan": output.action.steps}

    def route_after_replan(state: PlanExecuteState) -> str:
        if state.get("response"):
            return END
        if state.get("plan"):
            return "agent"
        return "replan"

    # ------------------------------------------------------------------
    # Graph wiring
    # ------------------------------------------------------------------

    workflow = StateGraph(PlanExecuteState)
    workflow.add_node("planner", plan_node)
    workflow.add_node("agent", execute_node)
    workflow.add_node("replan", replan_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "agent")
    workflow.add_edge("agent", "replan")
    workflow.add_conditional_edges(
        "replan",
        route_after_replan,
        {END: END, "agent": "agent", "replan": "replan"},
    )

    return workflow.compile(checkpointer=MemorySaver())


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

async def run_agent(task_data: dict) -> dict:
    task_id = task_data.get("task_id", "unknown")
    task = task_data.get("task", "")
    thread_id = f"{AGENT_ID}:{task_id}"
    started_at = datetime.now().isoformat()

    llm = ChatAnthropic(
        model=CLAUDE_MODEL,
        api_key=ANTHROPIC_API_KEY,
        max_tokens=4096,
    )

    tools = get_all_tools()
    skills_context = load_skills_context()
    app = build_app(llm, tools, skills_context)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 30,
    }

    messages = []
    tool_calls_log = []
    final_output = ""
    status = "completed"
    error = None

    try:
        async for event in app.astream(
            {"input": task, "plan": [], "past_steps": [], "response": None},
            config=config,
        ):
            for node_name, node_output in event.items():
                if node_name == "planner":
                    messages.append({"role": "planner", "plan": node_output.get("plan", [])})

                elif node_name == "agent":
                    for step, result in node_output.get("past_steps", []):
                        messages.append({"role": "executor", "step": step, "result": result})
                        tool_calls_log.append({"step": step, "result": result[:300]})

                elif node_name == "replan":
                    if node_output.get("response"):
                        final_output = node_output["response"]
                    elif node_output.get("plan"):
                        messages.append({"role": "replanner", "updated_plan": node_output["plan"]})

    except Exception as exc:
        status = "failed"
        error = str(exc)
        final_output = f"Task failed: {error}"

    try:
        save_session(thread_id, {"task": task, "messages": messages})
    except Exception:
        pass

    return {
        "agent_id": AGENT_ID,
        "task_id": task_id,
        "status": status,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "messages": messages,
        "tool_calls": tool_calls_log,
        "final_output": final_output,
        "error": error,
    }


async def main():
    task_file = WORKSPACE / "task.json"

    if not task_file.exists():
        print("Waiting for task.json in /workspace...")
        while not task_file.exists():
            await asyncio.sleep(2)

    task_data = json.loads(task_file.read_text())
    print(f"[agent] Starting task {task_data.get('task_id', 'unknown')}")

    result = await run_agent(task_data)

    (WORKSPACE / "output.json").write_text(json.dumps(result, indent=2))
    print(f"[agent] Done. Status: {result['status']}")
    if result.get("final_output"):
        print(f"[agent] Output preview: {result['final_output'][:300]}")


if __name__ == "__main__":
    asyncio.run(main())
