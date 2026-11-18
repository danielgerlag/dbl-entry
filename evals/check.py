"""Regression gate for skill edits.

Runs the tasks with each task's own skill (several repeats, to absorb noise) and compares per-task pass rates
with the committed baseline in `baseline.json`. Exits 1 if a task that used to pass now mostly fails, or if the
mean score drops by more than the margin. `--update-baseline` records the current results instead.

    python check.py --skill dblentry-reporting            # after editing one skill
    python check.py --models gpt-5.4-mini --repeats 3     # everything
    python check.py --skill dblentry-reporting --update-baseline
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

from baselines import evaluate, load_skill
from tasks import ALL_TASKS

BASELINE = Path(__file__).parent / "baseline.json"
TASK_DROP = 0.5  # a task regresses when its pass rate falls by more than this


def run(model, tasks, repeats, workers):
    eps = evaluate(lambda t: load_skill(t.skill), tasks, repeats=repeats, model=model, workers=workers)
    result = {}
    for t in tasks:
        mine = [e for e in eps if e.task_id == t.id]
        result[t.id] = {
            "pass_rate": sum(e.score == 1.0 for e in mine) / len(mine),
            "mean": statistics.mean(e.score for e in mine),
            "repeats": len(mine),
            "failures": sorted({f for e in mine for f in e.failures})[:3],
        }
    return result


def compare(model, current, base, margin):
    regressions, improvements, new, slipped = [], [], [], []
    for tid, cur in current.items():
        old = base.get(tid)
        if old is None:
            new.append(tid)
            continue
        delta = cur["pass_rate"] - old["pass_rate"]
        if delta < -TASK_DROP:
            regressions.append((tid, old["pass_rate"], cur["pass_rate"], cur["failures"]))
        elif delta > TASK_DROP:
            improvements.append((tid, old["pass_rate"], cur["pass_rate"]))
        elif delta < 0:
            slipped.append((tid, old["pass_rate"], cur["pass_rate"]))
    shared = [t for t in current if t in base]
    mean_drop = 0.0
    if shared:
        mean_drop = (statistics.mean(base[t]["mean"] for t in shared)
                     - statistics.mean(current[t]["mean"] for t in shared))
    print(f"\n== {model}: {len(current)} tasks, mean score "
          f"{statistics.mean(c['mean'] for c in current.values()):.3f}"
          + (f" (baseline {statistics.mean(base[t]['mean'] for t in shared):.3f})" if shared else ""))
    for tid, o, c, f in regressions:
        print(f"  REGRESSION {tid}: pass rate {o:.2f} -> {c:.2f}  {'; '.join(f)[:120]}")
    for tid, o, c in slipped:
        print(f"  slipped    {tid}: pass rate {o:.2f} -> {c:.2f} (within noise tolerance)")
    for tid, o, c in improvements:
        print(f"  improved   {tid}: pass rate {o:.2f} -> {c:.2f}")
    for tid in new:
        print(f"  new (no baseline) {tid}: pass rate {current[tid]['pass_rate']:.2f}")
    failed = bool(regressions) or mean_drop > margin
    if mean_drop > margin:
        print(f"  MEAN DROP {mean_drop:.3f} exceeds margin {margin}")
    return failed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-5.4-mini", help="comma-separated agent models")
    ap.add_argument("--skill", help="only tasks for this skill (default: all tasks)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--margin", type=float, default=0.03, help="allowed drop in mean score")
    ap.add_argument("--update-baseline", action="store_true", help="record results as the new baseline")
    a = ap.parse_args()

    tasks = [t for t in ALL_TASKS if not a.skill or t.skill == a.skill]
    if not tasks:
        sys.exit(f"no tasks for skill {a.skill!r}")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}

    failed = False
    for model in a.models.split(","):
        current = run(model, tasks, a.repeats, a.workers)
        if a.update_baseline:
            baseline.setdefault(model, {}).update(current)
            print(f"baseline updated for {model}: {len(current)} tasks")
        else:
            if model not in baseline:
                print(f"\n== {model}: no baseline yet; run with --update-baseline")
                continue
            failed |= compare(model, current, baseline[model], a.margin)

    if a.update_baseline:
        BASELINE.write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    elif failed:
        print("\nFAILED: skill regression detected")
        sys.exit(1)
    else:
        print("\nOK: no regressions")
