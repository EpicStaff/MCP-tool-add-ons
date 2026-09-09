import os
import time
import json
import subprocess
from typing import Optional, List
from contextlib import ExitStack


from fastmcp import FastMCP
import interpreter
from loguru import logger
from pydantic import BaseModel, Field


# ===================================================================
# CONFIG
# ===================================================================

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 7001))

API_KEY = os.getenv("API_KEY")
LLM = os.getenv("LLM_MODEL", "gpt-4o")
TIMEOUT = int(os.getenv("MCP_OPEN_INTERPRETER_TIMEOUT_SECONDS", 300))
FORWARD_PORTS = [4200, 8000]

if not API_KEY:
    raise RuntimeError(
        "API_KEY environment variable is not set. "
        "The OpenInterpreter tool requires a valid API key to function."
    )

logger.info(f"Using model {LLM}")

# ===================================================================
# MCP SERVER STARTUP
# ===================================================================

# Initialize MCP server
mcp = FastMCP("OpenInterpreterTool")

# ===================================================================
# SYSTEM PROMPT
# ===================================================================

AGENT_SYSTEM_PROMPT = """
        You are a browser automation agent running inside a secure Linux container
        with virtual display `:99` and noVNC monitoring. Your mission is to safely
        execute browser automation tasks using Python.

        Environment:
        - Display: Xvfb (:99)
        - Browser: Chromium + driver
        - Libraries: Playwright (Chromium), Selenium, requests, Pillow, OpenCV, pandas
        - System tools: scrot, x11vnc, GTK3, libx11, libgl1-mesa-glx, fonts, novnc, websockify
        - Async runtime: You are already inside an event loop. Do not use asyncio.run() or sync_playwright().
        - Image analysis: use only your model's vision capabilities unless explicitly instructed.

        Behavior Guidelines:
        1. Do not close the browser unless instructed.
        2. Use:
            from browser_manager import start_browser
            browser, context, page = await start_browser()
            to start the browser, and
            from browser_manager import close_browser
            await close_browser()
            to close it.
        3. Retry each step up to 5 times if it fails; record error if still failing.
    """

# ===================================================================
# INPUT_SCHEMA
# ===================================================================


class BrowserToolInput(BaseModel):
    """
    Input schema for the browser automation tool.
    Expects a contextual description and a list of sequential natural language instructions.
    """

    context: Optional[str] = Field(
        None,
        description="High-level context or objective of the browser session (e.g., 'Check Python website functionality').",
    )

    instructions: List[str] = Field(
        ...,
        min_items=1,
        description="Ordered list of natural language instructions for browser actions.",
    )


# ===================================================================
# PORT FORWARDING
# ===================================================================


def start_port_forwarding():
    """Start socat port forwarding and return cleanup stack."""
    stack = ExitStack()
    for port in FORWARD_PORTS:
        cmd = ["socat", f"TCP-LISTEN:{port},fork", f"TCP:host.docker.internal:{port}"]
        logger.info(f"Forwarding localhost:{port} -> host.docker.internal:{port}")
        proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
        stack.callback(lambda p=proc: os.killpg(os.getpgid(p.pid), 15))
    return stack


# ===================================================================
# TOOL
# ===================================================================


@mcp.tool(name="browser_tool")
def browser_tool(input_data: BrowserToolInput):
    """
    Expects task in format:
    {
        "context": "useful info for the tool",
        "instructions": [
            "Open the browser",
            "Open Python's main page",
            "Open Downloads page",
            "Check if it's working as intended"
        ]
    }
    """
    port_stack = start_port_forwarding()
    try:

        try:
            local_interpreter = interpreter.OpenInterpreter()
        except Exception as e:
            logger.error(f"Failed to initialize OpenInterpreter: {e}")
            return {"error": f"Interpreter init failed: {str(e)}"}

        local_interpreter.llm.api_key = API_KEY
        local_interpreter.llm.model = LLM
        local_interpreter.llm_supports_vision = True

        local_interpreter.display = False
        local_interpreter.stream = True

        local_interpreter.auto_run = True
        local_interpreter.safe_mode = False
        local_interpreter.offline = False
        local_interpreter.verbose = True
        local_interpreter.max_output = 2000

        system_prompt = AGENT_SYSTEM_PROMPT

        logger.info("Local Open Interpreter initialized.")

        context = input_data.context
        instructions = input_data.instructions

        if context:
            system_prompt += f"\n\n Task Context:\n{context}"

        local_interpreter.system_message = system_prompt

        logger.info(f"Received task: context: {context}; instructions: {instructions}")
        start_time = time.time()

        steps_output = []
        step_counter = 1

        for instruction in instructions:
            last_text = []
            step_summary = None
            step_success = True
            try:
                for chunk in local_interpreter.chat(instruction):
                    ctype = chunk.get("type")
                    content = chunk.get("content", "")

                    if content:
                        if ctype in ("code", "console"):
                            last_text = []
                        elif ctype == "message":
                            last_text.append(content)

            except Exception as e:
                step_summary = f"[FAILURE] Exception: {str(e)}"
                step_success = False

            else:
                step_summary = "".join(last_text).strip()

            steps_output.append(
                {"step": step_counter, "success": step_success, "summary": step_summary}
            )
            if not step_success:
                break
            step_counter += 1

        duration = round(time.time() - start_time, 2)
        result = {
            "steps": steps_output,
            "context": context,
            "duration_seconds": duration,
        }

        logger.info(
            f"Browser tool final output (agent-facing): {json.dumps(result, indent=2)}"
        )
        return result

    finally:
        port_stack.close()


# ===================================================================
# SERVER ENTRYPOINT
# ===================================================================

if __name__ == "__main__":
    logger.info(f"Starting OpenInterpreterTool server on http://0.0.0.0:{PORT}")

    mcp.run(transport="http", host=HOST, port=PORT)
