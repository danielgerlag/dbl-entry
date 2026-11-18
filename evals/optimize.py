"""Optimize a DblEntry skill with GEPA against real agents.

The candidate is the skill body (frontmatter is kept fixed). Each evaluation runs full agent episodes
(one per agent model) against fresh ledgers and averages the end-state scores. Candidates that leak
fixture specifics are penalized. Tasks come from `tasks.py`, filtered to the skill under optimization.
"""
import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gepa.optimize_anything as oa

from baselines import evaluate, load_skill, summarize
from harness import run_episode
from llm import REFLECTION_MODEL, complete
from tasks import ALL_TASKS, BY_ID

OUT = Path(__file__).parent / "out"

OBJECTIVE = (
    "Improve a SKILL document that is given to an LLM agent as guidance for using the DblEntry double-entry "
    "ledger through MCP tools (execute_fql, get_balance, get_schema, get_fql_spec, ...). Success means the "
    "agent leaves the ledger in the correct state, or gives the correct figures, for unseen requests, using "
    "few tool calls. The skill's topic: {description}"
)
BACKGROUND = (
    "Rules for the skill: it must stay GENERAL. Never copy names, amounts, dates, or account ids from the "
    "failing examples into the skill as if they were facts; abstract the lesson into a general rule or a "
    "generic illustrative pattern. Keep it concise and well structured markdown. Keep correct FQL syntax "
    "that already works. Do not state a rule unless the transcripts support it. Typical agent mistakes worth "
    "addressing when you see them in the feedback: guessing values (rates, account ids, dimension keys) "
    "instead of looking them up, inventing syntax, inventing dimensions that were not asked for, "
    "re-posting journals that already succeeded when retrying, and giving up (reporting 'no data') before "
    "exhausting the obvious alternatives."
)
COMMON_WORDS = {"Record", "Acme", "Customer", "Region"}


def split_tasks(skill):
    tasks = [t for t in ALL_TASKS if t.skill == skill]
    val = tasks[1::3]
    train = [t for t in tasks if t not in val]
    return train, val, tasks


def fixture_tokens():
    toks = set()
    for t in ALL_TASKS:
        toks |= set(re.findall(r"=\s*'([^']{3,})'", t.setup + " " + t.solution))  # dimension values
        toks |= set(re.findall(r"'([^']{3,})'", t.prompt))  # names quoted in prompts
        toks |= {n for n in re.findall(r"\b\d[\d,]{3,}\b", t.prompt)}
    return {x for x in toks if x not in COMMON_WORDS and not re.fullmatch(r"(19|20)\d\d", x)}


FIXTURE = fixture_tokens()


def leaked(candidate, seed):
    def has(tok, text):
        return re.search(rf"(?<![\w.]){re.escape(tok)}(?![\w])", text) is not None
    return sorted(tok for tok in FIXTURE if has(tok, candidate) and not has(tok, seed))


def make_evaluator(seed_text, models):
    def evaluator(candidate, example):
        task = BY_ID[example]
        with ThreadPoolExecutor(len(models)) as ex:
            eps = list(ex.map(lambda m: run_episode(task, candidate, model=m), models))
        mean = sum(e.score for e in eps) / len(eps)
        leaks = leaked(candidate, seed_text)
        info = {"task": task.prompt, "mean_score": mean}
        for m, e in zip(models, eps):
            info[m] = {"score": e.score, "failed_checks": e.failures or "none",
                       "tool_errors": e.tool_errors[:5] or "none", "turns": e.turns,
                       "transcript": e.transcript[:2500]}
        if leaks:
            info["PENALTY"] = f"Skill leaks task-specific details {leaks}; keep the skill general."
        return mean * (0.5 if leaks else 1.0), info
    return evaluator


def reflect(prompt):
    if not isinstance(prompt, str):
        prompt = "\n\n".join(m["content"] for m in prompt)
    r = complete(REFLECTION_MODEL, [{"role": "user", "content": prompt}], temperature=0.7)
    return r.choices[0].message.content


def split_frontmatter(text):
    m = re.match(r"(---\n.*?\n---\n)(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def description(frontmatter):
    m = re.search(r"description:\s*(.+)", frontmatter)
    return m.group(1).strip() if m else ""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", default="dblentry-record-transactions")
    ap.add_argument("--models", default="gpt-5.4-mini,gpt-5-nano", help="comma-separated agent models")
    ap.add_argument("--budget", type=int, default=60, help="max evaluations (each runs every model once)")
    ap.add_argument("--repeats", type=int, default=1, help="repeats for the final comparison")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    models = a.models.split(",")

    OUT.mkdir(exist_ok=True)
    text = load_skill(a.skill)
    fm, seed_body = split_frontmatter(text.replace("\r\n", "\n"))
    train, val, tasks = split_tasks(a.skill)
    print(f"skill={a.skill} models={models}\n train={[t.id for t in train]}\n val={[t.id for t in val]}", flush=True)

    cfg = oa.GEPAConfig(
        engine=oa.EngineConfig(max_metric_calls=a.budget, max_workers=a.workers,
                               run_dir=str(OUT / f"gepa-{a.skill}"), raise_on_exception=False),
        reflection=oa.ReflectionConfig(reflection_lm=reflect, reflection_minibatch_size=2),
    )
    result = oa.optimize_anything(
        seed_candidate=seed_body,
        evaluator=make_evaluator(seed_body, models),
        dataset=[t.id for t in train], valset=[t.id for t in val],
        objective=OBJECTIVE.format(description=description(fm)), background=BACKGROUND, config=cfg,
    )
    best = result.best_candidate
    best = best if isinstance(best, str) else next(iter(best.values()))
    out_path = OUT / f"{a.skill}.optimized.md"
    out_path.write_text(fm + best, encoding="utf-8")
    print(f"\nWrote {out_path}  (leaks: {leaked(best, seed_body)})", flush=True)

    for m in models:
        for label, body in (("none", ""), ("seed", seed_body), ("optimized", best)):
            summarize(f"{m} / {label} / held-out val",
                      evaluate(body, val, repeats=a.repeats, model=m, workers=a.workers))
        for label, body in (("seed", seed_body), ("optimized", best)):
            summarize(f"{m} / {label} / all {a.skill} tasks",
                      evaluate(body, tasks, repeats=a.repeats, model=m, workers=a.workers))
