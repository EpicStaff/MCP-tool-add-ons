# Computer Interaction Tools

Three MCP tools that let an agent act on a real environment: run CLI commands, drive a browser, or operate a full desktop GUI.

| Tool | Container(s) | Port | Underlying tech |
|---|---|---|---|
| **CLI Tool** | `cli_open_interpreter` | `7001` | Open Interpreter |
| **Browser Tool** | `browser_open_interpreter` | `7002` | Open Interpreter + Playwright/Chromium |
| **GUI Tool** | `open_computer_use` + `desktop` | `7003` | os-computer-use agent + Ubuntu desktop sandbox |

**Contents:** [Setup](#setup) · [Ports](#ports) · [Access](#access) · [Functionality](#functionality) · [Notes](#notes--safety)

---

## Setup

**1. Copy the template env file:**

```bash
cp template.env .env
```

**2. Fill in these fields in `.env` with actual info:**

```text
API_KEY=<your_api_key>
LLM_MODEL=<your_llm_choice>
```

> `API_KEY` and `LLM_MODEL` are shared by the **CLI** and **Browser** tools (Open Interpreter). The **GUI Tool** (`open_computer_use`) is configured separately via the `OCU_*` variables already present in `template.env` — grounding/vision/action provider and model, defaulted to `showui`/`deepseek`, plus `OCU_DESKTOP_NOVNC_PORT` (`6081`) pointing at the `desktop` sandbox's noVNC port — and reuses the same `API_KEY`.

**3. Navigate to the `computer_interaction_tools` folder and start the server(s):**

```bash
# Everything
docker compose up --build
```

| Want just... | Run |
|---|---|
| CLI tool | `docker compose up cli_open_interpreter --build` |
| Browser Use tool | `docker compose up browser_open_interpreter --build` |
| GUI Tool | `docker compose up desktop --build`<br>`docker compose up open_computer_use --build` |

---

## Ports

After startup, these ports are exposed:

| Port | Purpose |
|---|---|
| `7001` | CLI tool API |
| `7002` | Browser Use tool API |
| `7003` | GUI Tool API |
| `6080` | noVNC for the **Browser** tool (`browser_open_interpreter`) — `http://127.0.0.1:6080/vnc.html` |
| `5900` | Raw VNC for the **Browser** tool |
| `6081` | noVNC for the **GUI** tool's desktop sandbox (`desktop`) — `http://127.0.0.1:6081/vnc.html` |
| `5901` | Raw VNC for the **GUI** tool's desktop sandbox |

> `browser_open_interpreter` and `desktop` each run their own VNC/noVNC stack, so they're mapped to distinct host ports (`5900`/`6080` vs `5901`/`6081`) to avoid a `port is already allocated` conflict when both are started together (e.g. via `docker compose up --build`).

---

## Access

### HTTP requests

Send manual requests directly to each tool's MCP endpoint:

<details>
<summary><b>CLI tool request</b></summary>

```bash
curl -N -X POST http://localhost:7001/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "cli_tool",
      "arguments": {
        "input_data": {
          "context": "Optional context",
          "command": "Your command"
        }
      }
    },
    "id": 1
  }'
```
</details>

<details>
<summary><b>Browser Use tool request</b></summary>

```bash
curl -N -X POST http://localhost:7002/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "browser_tool",
      "arguments": {
        "input_data": {
          "context": "Optional context",
          "instructions": ["List of your instructions"]
        }
      }
    },
    "id": 1
  }'
```
</details>

<details>
<summary><b>GUI Tool request</b></summary>

```bash
curl -N -X POST http://localhost:7003/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "computer_use_tool",
      "arguments": {
        "input_data": {
          "context": "Optional context",
          "instructions": ["List of your instructions"]
        }
      }
    },
    "id": 1
  }'
```
</details>

### Python example (as a custom tool in the EpicStaff UI)

> On Linux you'll need to additionally add this to the sandbox in `src/docker-compose.yaml`:
> ```yaml
> extra_hosts:
>   - "host.docker.internal:host-gateway"
> ```

<details>
<summary><b>CLI tool</b> — Python client + input schema</summary>

```python
import asyncio
import json
from fastmcp import Client

def serialize_response(resp) -> str:
    """
    Extract only the structured_content from a FastMCP tool response
    and serialize it as JSON.
    """
    try:
        if hasattr(resp, "structured_content") and resp.structured_content is not None:
            return json.dumps(resp.structured_content, ensure_ascii=False, indent=2)
        elif isinstance(resp, dict):
            return json.dumps(resp, ensure_ascii=False, indent=2)
        else:
            return str(resp)
    except Exception:
        return str(resp)

async def call_cli_tool(command: str, context: str = None):
    """Call the Open Interpreter CLI tool via FastMCP client."""
    url = "http://host.docker.internal:7001/mcp"
    payload = {
        "input_data": {
            "command": command
        }
    }
    if context:
        payload["input_data"]["context"] = context

    async with Client(transport=url, timeout=300, init_timeout=300) as client:
        response = await client.call_tool("cli_tool", payload)
        return serialize_response(response)

def main(command: str, context: str = None):
    """Run async call synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(call_cli_tool(command, context))
    loop.close()
    return result
```

Input description:

```json
{
  "properties": {
    "command": {
      "type": "string",
      "description": "Action that needs to be performed"
    },
    "context": {
      "type": "string",
      "description": "High-level context or goal"
    }
  },
  "required": [
    "command"
  ]
}
```
</details>

<details>
<summary><b>Browser Use tool</b> — Python client + input schema</summary>

```python
import asyncio
import json
from fastmcp import Client

def serialize_response(resp) -> str:
    """
    Extract only the structured_content from a FastMCP tool response
    and serialize it as JSON.
    """
    try:
        if hasattr(resp, "structured_content") and resp.structured_content is not None:
            return json.dumps(resp.structured_content, ensure_ascii=False, indent=2)
        elif isinstance(resp, dict):
            return json.dumps(resp, ensure_ascii=False, indent=2)
        else:
            return str(resp)
    except Exception:
        return str(resp)

async def call_browser_tool(context: str, instructions: list):
    """Call the Open Interpreter browser tool via FastMCP client."""
    url = "http://host.docker.internal:7002/mcp"
    async with Client(transport=url, timeout=300, init_timeout=300) as client:
        response = await client.call_tool(
            "browser_tool",
            {
                "input_data": {
                    "context": context,
                    "instructions": instructions
                }
            }
        )
        return serialize_response(response)

def main(context: str, instructions: list):
    """Run async call synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(call_browser_tool(context, instructions))
    loop.close()
    return result
```

Input description:

```json
{
  "properties": {
    "context": {
      "type": "string",
      "description": "High-level context or objective of the browser session (e.g., 'Check Python website functionality')"
    },
    "instructions": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Ordered list of instructions the browser tool must perform"
    }
  },
  "required": [
    "context",
    "instructions"
  ]
}
```
</details>

<details>
<summary><b>GUI Tool</b> — Python client + input schema</summary>

```python
import asyncio
import json
from fastmcp import Client

def serialize_response(resp) -> str:
    """
    Extract only the structured_content from a FastMCP tool response
    and serialize it as JSON.
    """
    try:
        if hasattr(resp, "structured_content") and resp.structured_content is not None:
            return json.dumps(resp.structured_content, ensure_ascii=False, indent=2)
        elif isinstance(resp, dict):
            return json.dumps(resp, ensure_ascii=False, indent=2)
        else:
            return str(resp)
    except Exception:
        return str(resp)

async def call_gui_tool(context: str, instructions: list):
    """Call the GUI tool via FastMCP client."""
    url = "http://host.docker.internal:7003/mcp"
    async with Client(transport=url, timeout=300, init_timeout=300) as client:
        response = await client.call_tool(
            "computer_use_tool",
            {
                "input_data": {
                    "context": context,
                    "instructions": instructions
                }
            }
        )
        return serialize_response(response)

def main(context: str, instructions: list):
    """Run async call synchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(call_gui_tool(context, instructions))
    loop.close()
    return result
```

Input description:

```json
{
  "properties": {
    "context": {
      "type": "string",
      "description": "High-level context or goal for the browser session (e.g., 'Check Python website functionality')"
    },
    "instructions": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Ordered list of instructions the browser tool must perform"
    }
  },
  "required": [
    "context",
    "instructions"
  ]
}
```
</details>

---

## Functionality

### CLI Tool
- Converts natural-language instructions into shell commands or Python code
- Executes commands and returns output and errors

### Browser Tool
- Automates browser interactions in headful mode
- Executes a sequence of instructions
- GUI available at `http://127.0.0.1:6080/vnc.html`
- Browser is persistent within a single tool call — a new call starts a fresh browser

### GUI Tool
- Automates interactions with an Ubuntu system in a desktop sandbox
- Executes a sequence of instructions
- GUI available at `http://127.0.0.1:6081/vnc.html`
- Desktop sandbox should be launched separately and runs until stopped by the user
- Every tool call uses the same desktop instance

---

## Notes — Safety

> [!WARNING]
> These tools do **not have any guardrails** regarding the code they execute. All commands are executed automatically, without any confirmation.
>
> While the tools are containerized, they **can still modify or delete files within the container, interact with the network, or use any credentials provided**.
>
> Be careful with what you ask the agent to do. These tools **can and will execute destructive commands** if instructed to do so.
