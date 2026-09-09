from os_computer_use.streaming import Sandbox
from os_computer_use.sandbox_agent import SandboxAgent
from os_computer_use.logging import Logger
import asyncio
import argparse
import os
import sys

from dotenv import load_dotenv

logger = Logger()


load_dotenv()


SYSTEM_PROMPT = """
You are a computer-use automation agent operating inside a Dockerized Ubuntu desktop that is streamed via noVNC. Your mission is to safely complete user objectives by interacting with the desktop through keyboard, mouse, and shell commands exposed by your tools.

Environment:
- Display: hardware-accelerated X11 session on DISPLAY=:0
- Browser: Firefox ESR (preinstalled and launchable via GUI or shell with `firefox-esr &`)
- Available tools: run_command, run_background_command, send_key, type_text, click, double_click, right_click, screenshot
- System utilities: xdotool, scrot, ffmpeg, curl, wget, python3, pip, unzip
- File transfer: you can read screenshots that the host copies from `/tmp/ocu-screenshot.png`
- Logging: every action, observation, and screenshot is persisted to `output/run_<n>/log.html`

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


async def start(user_input=None, output_dir=None):
    sandbox = None
    running = True

    try:
        logger.log("Initializing sandbox...", "gray")
        sandbox = Sandbox()
        agent = SandboxAgent(sandbox, output_dir, system_prompt=SYSTEM_PROMPT)
        logger.log(
            f"Sandbox ready. Logs: {agent.tmp_dir if not agent else output_dir}", "gray"
        )

        while running:
            # Ask for user input, and exit if the user presses ctl-c
            if user_input is None:
                try:
                    user_input = input("USER: ")
                except KeyboardInterrupt:
                    print("\nStopping agent...")
                    running = False
                except EOFError:
                    print("\nNo input provided. Stopping agent...")
                    running = False
            # Run the agent, and go back to the prompt if the user presses ctl-c
            else:
                try:
                    logger.log(f"Running instruction: {user_input}", "blue")
                    agent.run(user_input)
                    logger.log("Instruction finished.", "green")
                    user_input = None
                except KeyboardInterrupt:
                    print("\nStopping agent...")
                    running = False
                except EOFError:
                    print("\nNo input provided. Stopping agent...")
                    running = False
                except Exception as e:
                    logger.print_colored(f"An error occurred: {e}", "red")
                    user_input = None

    finally:
        if sandbox:
            # print(
            #     "\nSandbox is still running. You can resume by running the agent again."
            # )
            # print(f"View the desktop at: http://localhost:6080/vnc.html")
            # sandbox.kill()  # Uncomment this line if you want to auto-stop the sandbox
            print("Sandbox is still running.")


def initialize_output_directory(directory_format):
    run_id = 1
    while os.path.exists(directory_format(run_id)):
        run_id += 1
    os.makedirs(directory_format(run_id), exist_ok=True)
    return directory_format(run_id)


def _normalize_base_output(raw_path: str | None) -> str:
    """Normalize host paths, especially Windows-style /c/... -> C:/..."""
    if not raw_path:
        return raw_path
    if os.name == "nt":
        # Convert /c/... or /C/... to C:/...
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, help="User prompt for the agent")
    args = parser.parse_args()

    if args.prompt is None and not sys.stdin.isatty():
        print("No prompt provided and stdin is not interactive. Exiting.")
        return

    raw_base_output = (
        os.getenv("MCP_SAVEFILES_PATH") or os.getenv("OUTPUT_DIR") or "./output"
    )
    base_output = _normalize_base_output(raw_base_output)
    output_dir = initialize_output_directory(lambda id: f"{base_output}/run_{id}")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start(user_input=args.prompt, output_dir=output_dir))
    except Exception as e:
        print(f"Fatal error: {e}")


if __name__ == "__main__":
    main()
