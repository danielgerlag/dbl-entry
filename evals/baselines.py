"""Baseline comparison: agent with no skill vs. the current skill text."""
import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness import run_episode
from mcp_client import ROOT
from tasks import SUITES

SKILL_DIR = ROOT / "crates" / "dblentry-mcp" / "skills"


def load_skill(name):
    return (SKILL_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def evaluate(skill_text, tasks, repeats=1, workers=6, model=None):
    """skill_text is a string, or a callable(task) -> string for per-task skills."""
    jobs = [(t, i) for t in tasks for i in range(repeats)]
    kw = {"model": model} if model else {}
    text_for = skill_text if callable(skill_text) else (lambda t: skill_text)
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda j: run_episode(j[0], text_for(j[0]), **kw), jobs))


def summarize(label, eps):
    mean = statistics.mean(e.score for e in eps)
    solved = sum(e.score == 1.0 for e in eps)
    print(f"\n== {label}: mean={mean:.3f} solved={solved}/{len(eps)} "
          f"avg_turns={statistics.mean(e.turns for e in eps):.1f} "
          f"avg_tool_errors={statistics.mean(len(e.tool_errors) for e in eps):.1f}")
    for e in eps:
        print(f"  {e.task_id:28s} {e.score:.2f} turns={e.turns:2d} errs={len(e.tool_errors)}  {'; '.join(e.failures)[:110]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", help="force one skill for every task (default: each task's own skill)")
    ap.add_argument("--suite", choices=list(SUITES), default="core")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--conditions", default="none,skill")
    ap.add_argument("--dump", help="write full transcripts to this json file")
    a = ap.parse_args()
    texts = {
        "none": "",
        "spec": "Before writing any FQL, call get_fql_spec, and call get_schema to see existing accounts.",
        "skill": lambda t: load_skill(a.skill or t.skill),
    }
    core_skill = a.skill or "dblentry-record-transactions"
    if (OPT := Path(__file__).parent / "out" / f"{core_skill}.optimized.md").exists():
        texts["optimized"] = OPT.read_text(encoding="utf-8")
    dump = {}
    for cond in a.conditions.split(","):
        eps = evaluate(texts[cond], SUITES[a.suite], repeats=a.repeats, model=a.model, workers=a.workers)
        summarize(cond, eps)
        dump[cond] = [e.__dict__ for e in eps]
    if a.dump:
        Path(a.dump).write_text(json.dumps(dump, indent=1), encoding="utf-8")
