"""Minimal synchronous MCP stdio client for the DblEntry server."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_exe = "dblentry.exe" if (ROOT / "target" / "debug" / "dblentry.exe").exists() else "dblentry"
DEFAULT_EXE = ROOT / "target" / "debug" / _exe


class McpClient:
    """Spawns `dblentry --mcp` (fresh in-memory ledger per instance)."""

    def __init__(self, exe=DEFAULT_EXE):
        self._p = subprocess.Popen(
            [str(exe), "--mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
        )
        self._n = 0
        self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "dblentry-evals", "version": "1"}})
        self._rpc("notifications/initialized", notify=True)

    def _rpc(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self._n += 1
            msg["id"] = self._n
        self._p.stdin.write(json.dumps(msg) + "\n")
        self._p.stdin.flush()
        if notify:
            return None
        while True:
            line = self._p.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed the stream")
            r = json.loads(line)
            if r.get("id") == self._n:
                return r

    def list_tools(self):
        return self._rpc("tools/list")["result"]["tools"]

    def call(self, name, arguments):
        """Returns (is_error, text)."""
        r = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in r:
            return True, r["error"].get("message", str(r["error"]))
        res = r["result"]
        text = "\n".join(c.get("text", "") for c in res.get("content", []))
        return bool(res.get("isError")), text

    def fql(self, query, entity=None):
        args = {"fql": query}
        if entity:
            args["entity"] = entity
        return self.call("execute_fql", args)

    def close(self):
        try:
            self._p.terminate()
            self._p.wait(timeout=5)
        except Exception:
            self._p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
