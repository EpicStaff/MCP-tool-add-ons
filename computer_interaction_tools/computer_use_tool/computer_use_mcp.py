import os
import time
import json
from typing import Optional, List
from pathlib import Path

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

from os_computer_use.streaming import Sandbox
from os_computer_use.sandbox_agent import SandboxAgent

# ===================================================================
# CONFIG
# ===================================================================

HOST = "0.0.0.0"
PORT = int(os.getenv("MCP_COMPUTER_USE_PORT", 7001))
DESKTOP_NOVNC_PORT = int(os.getenv("DESKTOP_NOVNC_EXTERNAL_PORT", 6081))


def _normalize_base_output(raw_path: str | None) -> str:
    """Normalize host paths, especially Windows-style /c/... -> C:/..."""
    if not raw_path:
        return raw_path
    if os.name == "nt":
        if (
            raw_path.startswith(("/", "\\"))
            and len(raw_path) > 2
            and raw_path[1].isalpha()
            and raw_path[2] in ("/", "\\")
        ):
            drive = raw_path[1].upper()
            remainder = raw_path[2:].lstrip("\\/")
            return f"{drive}:/{remainder}"
    return raw_path


OUTPUT_DIR = Path(
    _normalize_base_output(
        os.getenv("MCP_SAVEFILES_PATH") or os.getenv("OUTPUT_DIR") or "/app/output"
    )
)

logger.info(f"Starting Computer Use Tool MCP server on port {PORT}")

# ===================================================================
# MCP SERVER STARTUP
# ===================================================================

# Initialize MCP server
mcp = FastMCP("ComputerUseTool")

# ===================================================================
# SYSTEM PROMPT
# ===================================================================

AGENT_SYSTEM_PROMPT = """
You are a computer-use automation agent operating inside a Dockerized Ubuntu desktop that is streamed via noVNC. Your mission is to safely complete user objectives by interacting with the desktop through keyboard, mouse, and shell commands exposed by your tools.

Environment:
- Display: hardware-accelerated X11 session on DISPLAY=:0
- Browser: Firefox ESR (preinstalled and launchable via GUI or shell with `firefox-esr &`)
- Available tools: run_command, run_background_command, send_key, type_text, click, double_click, right_click, screenshot
- System utilities: xdotool, scrot, ffmpeg, curl, wget, python3, pip, unzip
- File transfer: you can read screenshots that the host copies from `/tmp/ocu-screenshot.png`
- Logging: every action, observation, and screenshot is persisted to the output directory

Behavior Guidelines:
1. Always keep the desktop usable; only reboot or terminate applications if required by the task.
2. When launching GUI applications (like Firefox), the system will automatically wait for them to fully render before taking the next screenshot.
3. Launch Firefox via `run_command("firefox-esr &")` - the system handles the wait time automatically.
4. Take a screenshot before issuing a `click`, `double_click`, or `right_click` so grounding has fresh context.
5. After every tool call, examine the observation before deciding the next action; stop as soon as the objective is complete.
6. If a command fails, retry up to 3 times with adjusted parameters; log persistent failures in the final response.
7. Never run `sudo` or modify Docker/network settings; treat the environment as shared infrastructure.
8. Firefox may show warnings about DBus/accessibility - these are normal and can be ignored.

Follow these rules strictly while pursuing the user's objective step by step.
"""

# ===================================================================
# INPUT_SCHEMA
# ===================================================================


class ComputerUseToolInput(BaseModel):
    """
    Input schema for the computer use automation tool.
    Expects a contextual description and a list of sequential natural language instructions.
    """

    context: Optional[str] = Field(
        None,
        description="High-level context or objective of the computer use session (e.g., 'Open Firefox and navigate to a website').",
    )

    instructions: List[str] = Field(
        ...,
        min_items=1,
        description="Ordered list of natural language instructions for computer actions.",
    )


# ===================================================================
# TOOL
# ===================================================================


@mcp.tool(name="computer_use_tool")
def computer_use_tool(input_data: ComputerUseToolInput):
    """
    Expects task in format:
    {
        "context": "useful info for the tool",
        "instructions": [
            "Open Firefox browser",
            "Navigate to python.org",
            "Take a screenshot",
            "Check if the page loaded correctly"
        ]
    }
    """
    sandbox = None
    output_dir = None

    try:
        # Initialize sandbox (this will start the docker container if needed)
        sandbox = Sandbox()

        # Create a temporary output directory for this run (under mounted output dir)
        output_base = OUTPUT_DIR
        output_base.mkdir(parents=True, exist_ok=True)
        run_id = 1
        while (output_base / f"run_{run_id}").exists():
            run_id += 1
        output_dir = str(output_base / f"run_{run_id}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Initialize the agent
        system_prompt = AGENT_SYSTEM_PROMPT
        if input_data.context:
            system_prompt += f"\n\n Task Context:\n{input_data.context}"

        agent = SandboxAgent(
            sandbox, output_dir, save_logs=True, system_prompt=system_prompt
        )

        logger.info(
            f"Received task: context: {input_data.context}; instructions: {input_data.instructions}"
        )
        start_time = time.time()

        steps_output = []
        step_counter = 1

        max_attempts = 3
        for instruction in input_data.instructions:
            step_success = False
            step_summary = None
            for attempt in range(1, max_attempts + 1):
                try:
                    # Run the agent with the instruction
                    agent.run(instruction)
                    step_summary = (
                        f"Successfully completed: {instruction} (attempt {attempt})"
                    )
                    step_success = True
                    break
                except Exception as e:
                    logger.error(f"Step {step_counter} attempt {attempt} failed: {e}")
                    step_summary = (
                        f"[FAILURE] Attempt {attempt}/{max_attempts}: {str(e)}"
                    )
                    if attempt == max_attempts:
                        step_success = False

            steps_output.append(
                {"step": step_counter, "success": step_success, "summary": step_summary}
            )
            if not step_success:
                break
            step_counter += 1

        duration = round(time.time() - start_time, 2)
        result = {
            "steps": steps_output,
            "context": input_data.context,
            "duration_seconds": duration,
            "output_dir": output_dir,
            "log_file": f"{output_dir}/log.html",
        }

        logger.info(
            f"Computer use tool final output (agent-facing): {json.dumps(result, indent=2)}"
        )
        return result

    except Exception as e:
        logger.error(f"Computer use tool execution failed: {e}")
        return {
            "error": f"Execution failed: {str(e)}",
            "steps": steps_output if "steps_output" in locals() else [],
            "context": input_data.context,
        }
    # finally:
    #     # Stop the sandbox after execution completes or fails
    #     if sandbox:
    #         try:
    #             logger.info("Stopping sandbox container...")
    #             sandbox.kill()
    #             logger.info("Sandbox container stopped successfully.")
    #         except Exception as e:
    #             logger.warning(f"Failed to stop sandbox container: {e}")


# ===================================================================
# SERVER ENTRYPOINT
# ===================================================================

if __name__ == "__main__":
    logger.info(f"Starting ComputerUseTool server on http://0.0.0.0:{PORT}")

    mcp.run(transport="http", host=HOST, port=PORT)
