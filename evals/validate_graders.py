"""Sanity-check the graders: the reference solution must score 1.0 and doing nothing must score < 1.0."""
from harness import grade
from mcp_client import McpClient
from tasks import ALL_TASKS, ENTITY

bad = 0
for t in ALL_TASKS:
    with McpClient() as c:
        c.fql(f"CREATE ENTITY '{ENTITY}'")
        if t.setup:
            err, text = c.fql(t.setup, entity=ENTITY)
            assert not err, f"{t.id} setup: {text}"
        empty, _ = grade(c, t, "")
        err, text = c.fql(t.solution, entity=ENTITY)
        full, fails = grade(c, t, " ".join(t.answer_contains))
        ok = not err and full == 1.0 and empty < 1.0
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {t.id:28s} empty={empty:.2f} solution={full:.2f}", "" if not err else text, fails)
raise SystemExit(bad)
