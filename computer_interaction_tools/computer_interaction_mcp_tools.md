# Computer Interaction Tools

## Setup
1. Copy the template env file:

~~~bash
cp template.env .env
~~~

2. Fill in this fields in .env file with actual info

~~~text
API_KEY=<your_api_key>
LLM_MODEL=<your_llm_choice>
~~~

`API_KEY` and `LLM_MODEL` are shared by the CLI and Browser tools (Open Interpreter). The GUI Tool (`open_computer_use`) is configured separately via the `OCU_*` variables in `template.env` (grounding/vision/action provider and model, defaulted to `showui`/`deepseek`) and reuses the same `API_KEY`.

3. Navigate to the `computer_interaction_tools` folder and start the server:

~~~bash
docker compose up --build
~~~

or

For CLI tool only
~~~bash
docker compose up cli_open_interpreter --build
~~~

For Browser Use tool only
~~~bash
docker compose up browser_open_interpreter --build
~~~


For GUI Tool Only
~~~bash
docker compose up desktop --build
docker compose up open_computer_use --build
~~~
---

## Ports
After startup, this ports are exposed:  

- `7001` – CLI tool API
- `7002` - Browser Use tool API
- `7003` - GUI Tool API
- `6080` - VNC server for browser GUI (Browser tool)
---

## Access

- **HTTP requests:** You can send manual requests via:

**CLI tool request:**
~~~bash
curl -N -X POST http://localhost:7001/mcp   -H "Content-Type: application/json"   -H "Accept: application/json, text/event-stream"   -d '{
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
~~~
**Browser Use tool request:**
~~~bash
curl -N -X POST http://localhost:7002/mcp   -H "Content-Type: application/json"   -H "Accept: application/json, text/event-stream"   -d '{
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
~~~

**GUI Tool request:**
~~~bash
curl -N -X POST http://localhost:7003/mcp   -H "Content-Type: application/json"   -H "Accept: application/json, text/event-stream"   -d '{
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
~~~

**Python example (as custom tool in UI):**

If working on Linux you'll need to additionally add this lines to sandbox in src/docker-compose.yaml:
~~~bash
    extra_hosts:
      - "host.docker.internal:host-gateway"
~~~
**CLI tool:**
Python code for tool
~~~python
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
~~~

Input Description
~~~json
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
~~~

**Browser Use tool:**
Python code for tool
~~~python
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
~~~

**GUI Tool:**
Python code for tool
~~~python
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
~~~

Input Description
~~~json
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
~~~
---

## Functionality
**CLI Tool**
- Converts natural-language instructions into shell commands or Python code
- Executes commands and returns output and errors

**Browser Tool**
- Automates browser interactions in headful mode
- Executes a sequence of instructions
- GUI available at http://127.0.0.1:6080/vnc.html
- Browser is persistant within single tool call. New call - fresh browser

**GUI Tool**
- Automates interactions with Ubuntu system in desktop sandbox
- Executes a sequence of instructions
- GUI available at http://127.0.0.1:6080/vnc.html
- Desktop sandbox should be launched separately and works until stoped by the user
- Every tool call will use same desktop instance

# Notes

These tools do **not have any guardrails** regarding the code they execute. All commands are executed automatically, without any confirmation.

While the tools are containerized, they **can still modify or delete files within the container, interact with the network, or use any credentials provided**.

Be careful with what you ask the agent to do. These tools **can and will execute destructive commands** if instructed to do so.
