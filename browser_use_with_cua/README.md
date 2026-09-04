# Browser Use with CUA

A containerized MCP server that drives a real Chromium browser inside a virtual X display (Xvfb + xfce4). The agent browses *headfully* — there is a real desktop behind it — so a human can attach over VNC and watch, or take over, while a task runs. This is a vendored rig extracted from the EpicStaff monorepo; it runs as its own standalone docker-compose stack.

## MCP tools

The running server (`fast_mcp_server.py`) exposes exactly two tools.

### `run_browser_use(prompt: str, next_prompt: str | None = None, session_id: str | None = None) -> dict`

Runs the browser-use agent against `prompt` (and `next_prompt`, if given). Appends both prompts to a per-session history file at `sessions/<session_id>.json`, then returns the runner's result dict with `session_id` added. If `session_id` is omitted, a fresh 8-hex-character id is generated (`os.urandom(4).hex()`) and returned so you can continue the same session.

### `restart_browser_use() -> dict`

Clears the in-memory session map, resets the browser session, runs `/app/restart.sh` (which kills and relaunches the X stack — `x11vnc`, `Xvfb`, `startxfce4`), sleeps 10 seconds, and returns `{status, stdout, stderr}`.

> **Caveat:** `restart_browser_use` tears down the X stack. Any live VNC viewer will drop and has to reconnect.

## Endpoint

Transport is `streamable-http`, bound to `0.0.0.0:8080` in the container and published as `8080:8080`.

MCP URL: `http://localhost:8080/mcp`

## Environment

Set these in `.env` (start from `.env.example`). Sourced from `docker-compose.yml` and `entrypoint.sh`.

| Variable | Default | Notes |
|---|---|---|
| `VNC_PASS` | **none — required** | Compose fails closed with `VNC_PASS must be set in .env`; `entrypoint.sh` independently checks it and exits 1. |
| `OPENAI_API_KEY` | none | Required in practice — the runner instantiates `ChatOpenAI(model="o3")`. |
| `DEEPSEEK_API_KEY` | none | Required in practice — see *Known quirk* below. |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Passed through by compose. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | Passed through by compose. |
| `DEEPSEEK_TEMPERATURE` | `0.0` | Passed through by compose. |
| `VNC_GEOMETRY` | `1600x900` | Virtual display size. Hardcoded in `docker-compose.yml`, so overriding it via `.env` has no effect unless you edit compose. |
| `RUNS_DIR` | `/app/runs` | Artifact directory inside the container. |
| `DISPLAY` | `:99` | The Xvfb display. |
| `START_TOOL` | `browser` | Read only by the unused orchestrator code. |
| `START_URL` | `about:blank` | Read only by the unused orchestrator code. |
| `CUA_USE_LOCAL` | `1` | Read only by the unused computer-use code. |
| `CUA_CONTAINER_NAME` | `browser_use_with_cua` | Read only by the unused computer-use code. |

**Known quirk.** `app_browser_use/browser_runner.py` reads `DEEPSEEK_API_KEY` at import time and calls `exit(1)` if it is unset — but the DeepSeek LLM path directly below it is commented out, and `ChatOpenAI(model="o3")` is used instead. So today you need *both* keys: the OpenAI key is actually used, and the DeepSeek key is only checked, never used. Not fixed here.

## Run

From this directory:

```bash
cp .env.example .env    # then fill in VNC_PASS, OPENAI_API_KEY, DEEPSEEK_API_KEY
docker compose build
docker compose up -d
docker compose logs -f
```

Optional smoke test — an interactive fastmcp client that calls `run_browser_use` in a loop:

```bash
python test_client.py
```

It honours `FASTMCP_URL` and defaults to `http://127.0.0.1:8080/mcp`.

## Watching the browser (VNC)

Port `5900` is published, so any VNC client — RealVNC Viewer, Remmina, `vncviewer` — can attach:

```
localhost:5900
```

The password is **whatever you set as `VNC_PASS` in your `.env`**. There is no fixed or default password; the container will not start without one.

## State on disk

- `sessions/` — one `<session_id>.json` per session holding the prompt history. This lives **inside the container only**; it is not volume-mounted, so it is lost whenever the container is recreated.
- `runs/` — bind-mounted as `./runs:/app/runs`. This is the only artifact path that survives on the host.

## What actually runs

| Path | Role |
|---|---|
| `fast_mcp_server.py` | The entrypoint — Dockerfile `CMD` and compose `command` both point here. Roughly half the file is commented-out orchestrator code; ignore it. |
| `app_browser_use/browser_runner.py` | The code that actually executes browser tasks. |
| `entrypoint.sh`, `restart.sh`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `installer.sh` | Runtime and build. |

Not reached by the running container — kept for reference, nothing in the compose stack starts them:

| Path | What it is |
|---|---|
| `app_browser_use/fast_mcp_server.py` | A separate server exposing a `run_browser` tool. |
| `app_computer_use/` | Its own MCP server exposing `run_computer`, plus vendored computer-use code. |
| `orchestrator/` | Multi-step planner/supervisor layer. |
| `mcp_node/` | A standalone fastmcp *client* harness. |
| `prompt.py`, `test/`, `test_*.py`, `scripts/` | Ad-hoc prompts, tests, and helper scripts. |
