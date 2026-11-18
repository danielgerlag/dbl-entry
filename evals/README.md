# Skill evals

Measures and improves the MCP agent skills (`crates/dblentry-mcp/skills/`) against a real LLM agent, using
[GEPA](https://github.com/gepa-ai/gepa) for reflective prompt evolution.

Each episode starts a fresh in-memory `dblentry --mcp`, gives a tool-calling agent a bookkeeping request, then
grades the **ledger end state** deterministically (balances by account, dimension and date). No LLM judge.

```
python -m pip install -r requirements.txt
cargo build                      # evals use target/debug/dblentry
python validate_graders.py       # every task's reference solution must score 1.0
python baselines.py --conditions none,spec,skill
python baselines.py --suite all --conditions none,skill --model gpt-5.4-mini --workers 3
python optimize.py --skill dblentry-reporting --models gpt-5.4-mini,gpt-5-nano --budget 40  # writes out/<skill>.optimized.md (never overwrites the real skill)
python check.py --skill dblentry-reporting   # regression gate after editing a skill (exit 1 on regression)
```

**Regression gate.** `check.py` runs each task with its own skill (3 repeats by default) and compares pass rates
with the committed `baseline.json`. It fails if a task that used to pass now fails most repeats, or if the mean
score drops by more than `--margin` (0.03). Small slips are listed but tolerated, since runs are noisy. After an
intentional improvement, record it with `python check.py --update-baseline` (add `--skill` to refresh one skill,
`--models a,b` for other agents). The baseline is per agent model; `gpt-5.4-mini`, `Kimi-K2.6` and `DeepSeek-V4-Flash` are recorded (check them with `--models`).
It needs the same Foundry access as the other evals, so it is run by hand rather than in CI.

LLM access uses Azure CLI credentials against a Microsoft Foundry endpoint (`az login` first). Copy
`.env.example` to `.env` (gitignored) and set `EVAL_ENDPOINT`, `EVAL_SUBSCRIPTION`, `EVAL_AGENT_MODEL` (the agent
under test) and `EVAL_REFLECTION_MODEL` (GEPA's reflector). `--model` overrides the agent per run. On Windows
set `PYTHONUTF8=1`. Some deployments have small token-per-minute quotas; use `--workers 2-3` and the client
backs off on 429s. Don't start several runs in the same second: concurrent `az` token refreshes can fail on a
cache lock.

- `tasks.py` - fixtures, prompts and graders. Fixture specifics live only here and are penalized if they leak
  into a candidate skill. Two suites (`--suite core|advanced|all`): `core` is 12 transaction-recording tasks;
  `advanced` is 13 harder tasks for the accruals, multi-currency/units and reporting skills. Under `skill`,
  each task gets its own skill unless `--skill` forces one.
- `harness.py` - agent loop and grading; `baselines.py` - none / spec-only / skill / optimized comparison.
- `optimize.py` - GEPA `optimize_anything` with a train/val split.

Strong agents (Kimi-K2.6, DeepSeek-V4-Flash, gpt-5.4-mini) mostly solve even the core tasks without a skill, so
compare **turns and tool errors** as well as score. The advanced suite is where they still stumble, and its
failures have already corrected the skills (annual-rate accrual, rate lookup, dimension-key casing, even vs
prorated schedules).

Always review an optimized skill by hand before adopting it: with a small task set GEPA can overfit or add
spurious rules.
