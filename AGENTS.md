# AGENTS.md

## Cursor Cloud specific instructions

DblEntry is a single-product Rust workspace: a "Layer 2" double-entry bookkeeping engine
exposing REST + FQL-over-HTTP (and optional gRPC/MCP), plus a Vue 3 web console in `ui/`.
Standard build/test/lint/run commands live in the `Makefile` (and `readme.md`); prefer those.

### Services
- Backend (Rust/axum): `make run` (= `cargo run -- --port 3001`). Health at `GET /health`,
  FQL at `POST /fql` (text/plain body), REST under `/api/...`, metrics at `/metrics`.
  Storage defaults to in-memory, so no database is needed for a normal dev run — but data is
  lost on restart.
- Web UI (Vite): `cd ui && npm run dev` → http://localhost:5173. It proxies `/fql`, `/api`,
  `/health`, `/metrics` to the backend, defaulting to `http://localhost:3001`
  (override with `DBLENTRY_API_URL`). Run the backend first, then the UI.
- `make demo` runs backend + UI together.

### Non-obvious caveats
- Toolchain: building requires Rust with `edition2024` support (>= 1.85) because
  `rmcp-macros` pulled in by `crates/dblentry-mcp` needs it; the pod's default `stable`
  toolchain is fine. The build also requires `protoc` (`build.rs` compiles
  `proto/dblentry.proto` via tonic-build); it is preinstalled in this environment.
- Lint/format currently FAIL on `master` and this is pre-existing (GitHub CI is red for the
  same reason), not an environment problem: `cargo fmt --all -- --check` reports ~700 diffs,
  and `cargo clippy --all-targets -- -D warnings` reports `result_large_err` errors that
  originate only in the generated tonic proto code (`target/.../out/dblentry.v1.rs`), not in
  hand-written source. `cargo test` passes (123 tests; 17 Postgres tests are `#[ignore]`d).
- Postgres-gated integration tests (`cargo test -- --include-ignored`) need a Postgres
  instance via `docker compose -f docker-compose.test.yml up -d`; Docker is not installed by
  default here, so these stay skipped unless you install it.
