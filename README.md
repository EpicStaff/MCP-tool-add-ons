# EpicStaff MCP Tools add-ons

[MCP](https://modelcontextprotocol.io) servers extracted from the EpicStaff monorepo's `src/tool/custom_tools/`, which has since been deleted from EpicStaff, plus `computer_interaction_tools`, a later add-on group. Each group runs as its own docker-compose stack, independent of EpicStaff's, and is reachable over HTTP by any MCP client.

Each gives an LLM agent a capability it cannot have on its own: `git_tools` lets it work a pull request end to end, `browser_use_with_cua` lets it drive a real web browser, and `computer_interaction_tools` lets it run CLI commands, drive a browser, or operate a full desktop GUI.

## What's in here

### `git_tools` — pull-request automation for GitHub and GitLab

An MCP server exposing 14 tools that cover a code-review workflow: reading what changed, and writing back the verdict.

- **Read** — list open / recent / unlabeled PRs, fetch specific ones by number, list what merged since the last release, and pull a PR's diff and changed-file list.
- **Write** — post general, review, and line-anchored inline comments, apply labels, rewrite the description, and open a draft release with generated notes.

The same 14 tools serve **both platforms**: every call takes `client_type: "github" | "gitlab"`, and the server routes to PyGithub or python-gitlab behind a common client interface. An agent written against it doesn't care which platform the repo lives on.

Credentials arrive as a `token` argument on each call, which is why the server ships an **outbound URL allow-list** (`GIT_TOOLS_ALLOWED_URLS`) that refuses to send that token anywhere off-list, and blocks allow-listed hosts that resolve to private or link-local addresses. See [`git_tools/README.md`](git_tools/README.md) for the details and for the five agent system prompts it was built to serve — code review, PR summarizing, docs-needed detection, auto-labeling, and draft release notes.

### `browser_use_with_cua` — an agent that drives a real browser

An MCP server wrapping [browser-use](https://github.com/browser-use/browser-use): you hand it a task in plain language (`run_browser_use(prompt=...)`) and it navigates, clicks, and types in a real Chromium instance until the task is done or it gives up.

The browser runs **headfully** on a virtual X display (Xvfb + xfce4) inside the container, and port `5900` publishes that desktop over VNC — so you can watch the agent work in real time, or take the mouse and unstick it. Multi-step work is kept in a session: pass the `session_id` back on the next call to continue, or `restart_browser_use()` to wipe the state and relaunch the browser.

See [`browser_use_with_cua/README.md`](browser_use_with_cua/README.md).

### `computer_interaction_tools` — CLI, browser, and desktop GUI automation

A group of **3 MCP tools**, each its own container, that let an agent act directly on a real environment instead of only reasoning about it:

- **`cli_tool`** (`cli_open_interpreter`) — converts a natural-language instruction into shell commands or Python code via [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter) and returns stdout/stderr/exit code.
- **`browser_tool`** (`browser_open_interpreter`) — runs an ordered list of natural-language instructions against a real, headful Chromium browser (Playwright, on a virtual X display); the session is watchable live over noVNC and stays open across the instructions of one call.
- **`computer_use_tool`** (`open_computer_use`) — runs an ordered list of natural-language instructions against a full Ubuntu desktop (keyboard, mouse, shell, screenshots), also watchable over noVNC. It drives a separate **`desktop`** sandbox container that must be started alongside it and persists across tool calls until stopped.

None of these tools have guardrails: commands run automatically with no confirmation step, and — even though containerized — they can modify or delete files, reach the network, or use any credentials handed to them. Treat them as you would direct shell access.

See [`computer_interaction_tools/computer_interaction_mcp_tools.md`](computer_interaction_tools/computer_interaction_mcp_tools.md) for setup, ports, curl/Python call examples, and the full safety notes.

## Services

| Service | Entrypoint | Transport | Container port | Published | MCP URL |
|---|---|---|---|---|---|
| `git_tools` | `server.py` | http | 8000 | 8082 | `http://localhost:8082/mcp` |
| `browser_use_with_cua` | `fast_mcp_server.py` | streamable-http | 8080 | 8080 | `http://localhost:8080/mcp` |
| `cli_open_interpreter` | `cli_mcp.py` | http | 7001 | 7001 | `http://localhost:7001/mcp` |
| `browser_open_interpreter` | `browser_mcp.py` | http | 7002 | 7002 | `http://localhost:7002/mcp` |
| `open_computer_use` | `computer_use_mcp.py` | http | 7003 | 7003 | `http://localhost:7003/mcp` |
| `desktop` | — (VNC sandbox, no MCP endpoint) | — | 8080 / 5900 | 6081 / 5901 | — |

`browser_use_with_cua` also publishes `5900` for VNC. `browser_open_interpreter` also publishes `5900` (VNC) and `6080` (noVNC); `desktop` publishes `5901` (VNC) and `6081` (noVNC) — kept on different host ports from `browser_open_interpreter` so both can run at once without a port clash.

Each service is started on its own: `cd <service> && docker compose up -d`. There is no top-level compose file — **except** `computer_interaction_tools`, whose four containers (`cli_open_interpreter`, `browser_open_interpreter`, `open_computer_use`, `desktop`) share one `docker-compose.yaml` and are typically started together with `cd computer_interaction_tools && docker compose up --build` (each can still be started individually — see its own README).

## Connecting to EpicStaff

EpicStaff models MCP tools as **one database row per tool** (`McpTool`, endpoint `/mcp-tools/`). There is no "MCP server" entity. Register them in the UI at `/tools/mcp`; agents then attach them through the tools-selector, where ids are encoded as `mcp-tool:<id>`.

Fields on each row:

| Field | Notes |
|---|---|
| `name` | Display name. |
| `transport` | The server URL — see below. |
| `tool_name` | The MCP tool to call on that server. |
| `timeout` | Default `30`. |
| `auth_secret_id` | Optional; resolves through EpicStaff Secrets. |
| `init_timeout` | Default `10`. |

`transport` is a **URL string** (max 2048 chars), not an enum. It is handed straight to `fastmcp.Client`, which infers the transport from the value. There are no command / args / env fields, so **stdio servers cannot be configured from the UI** — only remote HTTP/SSE URLs. All services here are HTTP.

There is no test-connection button, no refresh-tools action, and no auto-discovery. Every tool is entered by hand.

### One row per tool

Because each row is a single tool, `git_tools` needs 14 entries that share the same `transport` and differ only by `tool_name`:

```
get_open_pull_requests
get_pull_requests_by_numbers
get_recent_pull_requests
get_merged_since_last_release
get_unlabeled_pull_requests
get_diff
get_changed_files
add_review_comment
add_inline_comment
add_comment
add_label
update_description
create_draft_release
get_pull_requests
```

`browser_use_with_cua` needs 2:

```
run_browser_use
restart_browser_use
```

`computer_interaction_tools` needs 3, one per container, each with its own `transport`:

```
cli_tool
browser_tool
computer_use_tool
```

### Networking

EpicStaff and these tools are **separate docker-compose projects on separate networks**. Typing `http://localhost:8082/mcp` into the EpicStaff UI resolves *inside the EpicStaff container*, where nothing is listening — it will fail.

Options, in no particular order:

- **`http://host.docker.internal:8082/mcp`** — on Linux this requires `extra_hosts: ["host.docker.internal:host-gateway"]` on the EpicStaff service.
- **A shared external docker network** — attach both stacks to it and address the service by name. Note this uses the **container** port, not the published one: `http://git-tools:8000/mcp`, not `8082`.
- **The host's LAN or docker-bridge IP** — e.g. `http://192.168.x.x:8082/mcp`.
- **A reverse proxy or public URL** in front of the services.

Pick one to suit your environment. These docs deliberately do not choose for you.

### Credentials

`auth_secret_id` resolves through EpicStaff's Secrets feature, and fastmcp sends the resolved value as an `Authorization` header.

That does not line up with what these services actually do:

- **`git_tools`** never reads request headers. Its `token` is a per-call **tool argument**, so the Secret path does nothing for it today and the token travels through the model's tool-call arguments.
- **`browser_use_with_cua`** has no auth at all. Anyone who can reach port `8080` gets remote browser control, and port `5900` is a full desktop behind only `VNC_PASS`.
- **`computer_interaction_tools`** has no auth either, and no `auth_secret_id`-style path at all — `API_KEY`/`LLM_MODEL` (and the GUI tool's `OCU_*` model settings) are container-side env vars, not per-call credentials. Anyone who can reach `7001`–`7003` gets unrestricted CLI/browser/desktop control, and the noVNC ports (`6080`, `6081`) have no password.

Do not expose any of these beyond a trusted network. All are noted here as follow-ups, not fixed in this checkpoint.

## Repository layout

- `git_tools/` — GitHub/GitLab pull-request and release MCP server.
- `browser_use_with_cua/` — headful browser-automation MCP server with VNC.
- `computer_interaction_tools/` — CLI, browser, and desktop-GUI computer-interaction MCP servers, plus the `desktop` sandbox container the GUI tool drives.
