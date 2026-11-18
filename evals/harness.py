"""Agent episode runner: a tool-calling LLM loop against a fresh `dblentry --mcp` ledger."""
import json
from dataclasses import dataclass

from llm import AGENT_MODEL, complete
from mcp_client import McpClient
from tasks import ENTITY, Task

HIDDEN_TOOLS = {"get_skill", "list_skills"}  # skills are injected into the prompt instead
MAX_TURNS = 14
MAX_TOOL_CHARS = 3500
MAX_SPEC_CHARS = 40000

BASE_PROMPT = (
    "You are an accounting assistant with access to a double-entry ledger through tools. "
    f"The ledger entity for this company is '{ENTITY}' (it already exists). "
    "Complete the user's request using the tools, then reply with a brief summary of what you did."
)


@dataclass
class Episode:
    task_id: str
    score: float
    failures: list
    tool_errors: list
    answer: str
    turns: int
    transcript: str


def _tools(client):
    out = []
    for t in client.list_tools():
        if t["name"] in HIDDEN_TOOLS:
            continue
        out.append({"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""), "parameters": t["inputSchema"]}})
    return out


def system_prompt(skill_text):
    if not skill_text:
        return BASE_PROMPT
    return f"{BASE_PROMPT}\n\n# Skill (follow this guidance)\n\n{skill_text}"


def grade(client, task: Task, answer: str):
    failures, passed, total = [], 0, 0
    try:
        checks = task.checks(client)
    except Exception as e:  # grader must never crash an episode
        checks = [(f"grader error: {e}", False)]
    for desc, ok in checks:
        total += 1
        passed += ok
        if not ok:
            failures.append(desc)
    for needle in task.answer_contains:
        total += 1
        if needle in answer.replace(",", ""):
            passed += 1
        else:
            failures.append(f"final answer should mention {needle}")
    return (passed / total if total else 0.0), failures


def run_episode(task: Task, skill_text: str = "", model: str = AGENT_MODEL) -> Episode:
    with McpClient() as c:
        c.fql(f"CREATE ENTITY '{ENTITY}'")
        if task.setup:
            err, text = c.fql(task.setup, entity=ENTITY)
            assert not err, f"setup failed for {task.id}: {text}"
        tools = _tools(c)
        messages = [{"role": "system", "content": system_prompt(skill_text)},
                    {"role": "user", "content": task.prompt}]
        log, tool_errors, answer, turns = [f"USER: {task.prompt}"], [], "", 0
        for turns in range(1, MAX_TURNS + 1):
            resp = complete(model, messages, tools=tools, temperature=0)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                answer = msg.content or ""
                log.append(f"ASSISTANT: {answer}")
                break
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                is_err, text = c.call(tc.function.name, args)
                if is_err:
                    tool_errors.append(f"{tc.function.name}: {text[:200]}")
                short = text[:MAX_SPEC_CHARS if tc.function.name == "get_fql_spec" else MAX_TOOL_CHARS]
                log.append(f"CALL {tc.function.name} {json.dumps(args)}\n  -> {'ERROR ' if is_err else ''}{short[:600]}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": short})
        score, failures = grade(c, task, answer)
        return Episode(task.id, score, failures, tool_errors, answer, turns, "\n".join(log))
