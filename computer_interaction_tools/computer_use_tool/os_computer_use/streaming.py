"""Docker-backed sandbox runtime and display helpers."""

import asyncio
import os
import shlex
import signal
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class SandboxError(RuntimeError):
    """Raised when the Docker desktop sandbox fails."""


@dataclass
class DockerCommandResult:
    stdout: str
    stderr: str


class DockerCommands:
    """Executes commands inside the desktop container."""

    def __init__(self, container_name: str, display: str):
        self.container_name = container_name
        self.display = display

    def _base_cmd(self) -> list[str]:
        return ["docker", "exec", "-e", f"DISPLAY={self.display}", self.container_name]

    def run(
        self, command: str, timeout: Optional[int] = None, background: bool = False
    ) -> DockerCommandResult:
        if background:
            wrapped = f"nohup bash -lc {shlex.quote(command)} >/tmp/ocu-bg.log 2>&1 &"
            subprocess.run(self._base_cmd() + ["bash", "-lc", wrapped], check=True)
            return DockerCommandResult(stdout="", stderr="")

        completed = subprocess.run(
            self._base_cmd() + ["bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return DockerCommandResult(
            stdout=(completed.stdout.strip() if completed.stdout else ""),
            stderr=(completed.stderr.strip() if completed.stderr else ""),
        )


class DockerStream:
    """Represents the browser-accessible VNC stream."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._started = False

    def start(self):
        self._started = True

    def get_url(self) -> str:
        if not self._started:
            raise SandboxError("Stream has not been started yet.")
        return f"http://{self.host}:{self.port}/vnc.html"


class Sandbox:
    """Controls the Docker-based desktop environment."""

    def __init__(self):
        # docker-compose.yaml is at the mcp_tools level (two parents up from computer_use_tool) by default
        self.project_root = Path(__file__).resolve().parents[2]
        default_compose = self.project_root / "docker-compose.yaml"

        # Allow overriding the compose file path or skipping compose entirely
        self.compose_file = Path(os.getenv("OCU_COMPOSE_FILE", default_compose))
        self.skip_compose = os.getenv("OCU_SKIP_COMPOSE", "0") in ("1", "true", "True")
        self.container_name = os.getenv("OCU_DESKTOP_CONTAINER", "ocu-desktop")
        # theasp/novnc uses DISPLAY=:0 by default
        self.display = os.getenv("OCU_DESKTOP_DISPLAY", ":0")
        print("Display Used:", self.display)
        self.stream_host = os.getenv("OCU_DESKTOP_HOST", "localhost")
        self.stream_port = int(os.getenv("OCU_DESKTOP_NOVNC_PORT", "6080"))
        self._ensure_container()
        self.commands = DockerCommands(self.container_name, self.display)
        self.stream = DockerStream(self.stream_host, self.stream_port)

    def _compose_cmd(self, *args: str) -> list[str]:
        if not hasattr(self, "_compose_command"):
            try:
                subprocess.run(
                    ["docker", "compose", "version"],
                    capture_output=True,
                    check=True,
                    timeout=5,
                )
                self._compose_command = ["docker", "compose"]
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._compose_command = ["docker-compose"]

        cmd = self._compose_command + ["-f", str(self.compose_file)] + list(args)
        return cmd

    def _ensure_container(self):
        """Start the desktop container if it is not already running."""
        if self.skip_compose:
            return

        if not self.compose_file.exists():
            raise SandboxError(f"docker-compose file not found at {self.compose_file}")

        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.container_name],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout.strip().lower() == "true":
                print(f"Container '{self.container_name}' is already running.")
                return
        except subprocess.CalledProcessError:
            print(
                f"Container '{self.container_name}' is not running. Attempting to start it."
            )

        # Start the container using docker-compose
        try:
            subprocess.run(
                self._compose_cmd("up", "-d", "desktop"),
                check=True,
                cwd=self.compose_file.parent,
            )
        except subprocess.CalledProcessError as exc:
            raise SandboxError(
                "Failed to start Docker desktop container. Is Docker running?"
            ) from exc

        # Wait for the noVNC endpoint to accept connections
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                with socket.create_connection(
                    (self.stream_host, self.stream_port), timeout=1
                ):
                    return
            except OSError:
                time.sleep(1)
        raise SandboxError(
            "Timed out waiting for the desktop stream to become available."
        )

    def _exec(self, command: str):
        self.commands.run(command)

    def screenshot(self) -> bytes:
        remote_path = "/tmp/ocu-screenshot.png"
        # Use ImageMagick's 'import' to capture the root window (includes all child windows)
        # -window root captures the entire screen including all windows
        # -quiet suppresses output, -quality 100 ensures high quality
        result = self.commands.run(
            f"sleep 0.5 && DISPLAY={self.display} import -window root -quality 100 {remote_path} 2>&1"
        )
        if result.stderr and "error" in result.stderr.lower():
            print(f"Warning: import stderr: {result.stderr}")
        if result.stdout:
            print(f"import stdout: {result.stdout}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp_path = Path(tmp.name)
        try:
            subprocess.run(
                ["docker", "cp", f"{self.container_name}:{remote_path}", str(tmp_path)],
                check=True,
            )
            # Verify the file was created and has content
            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                raise SandboxError(
                    f"Screenshot file is empty or missing: {remote_path}"
                )
            with open(tmp_path, "rb") as image_file:
                return image_file.read()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def set_timeout(self, *_):
        # The Docker container does not have an idle timeout, so no-op.
        return None

    def run_with_xdotool(self, command: str):
        self._exec(f"xdotool {command}")

    def press(self, combo: str):
        sequence = self._format_combo(combo)
        self.run_with_xdotool(f"key {sequence}")

    def write(self, text: str, chunk_size: int = 50, delay_in_ms: int = 12):
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            safe_chunk = shlex.quote(chunk)
            self._exec(
                f"xdotool type --delay {delay_in_ms} --clearmodifiers -- {safe_chunk}"
            )

    def move_mouse(self, x: int, y: int):
        self.run_with_xdotool(f"mousemove --sync {x} {y}")

    def left_click(self):
        self.run_with_xdotool("click 1")

    def double_click(self):
        self.run_with_xdotool("click --repeat 2 --delay 150 1")

    def right_click(self):
        self.run_with_xdotool("click 3")

    def scroll_up(self, amount: int = 1):
        """Scroll up by a specified amount."""
        self.run_with_xdotool(f"click --repeat {amount} 4")

    def scroll_down(self, amount: int = 1):
        """Scroll down by a specified amount."""
        self.run_with_xdotool(f"click --repeat {amount} 5")

    def kill(self):
        subprocess.run(["docker", "rm", "-f", self.container_name], check=False)

    @staticmethod
    def _format_combo(combo: str) -> str:
        parts = combo.replace("+", "-").split("-")
        mapped = []
        for part in parts:
            normalized = part.lower()
            replacements = {
                "ctl": "ctrl",
                "ctrl": "ctrl",
                "control": "ctrl",
                "alt": "alt",
                "cmd": "super",
                "win": "super",
                "shift": "shift",
                "enter": "Return",
                "return": "Return",
                "esc": "Escape",
            }
            if normalized in replacements:
                mapped.append(replacements[normalized])
            else:
                mapped.append(part)
        return "+".join(mapped)


# Client to view and save a live display stream from the sandbox (unchanged)
class DisplayClient:
    def __init__(self, output_dir="."):
        self.process = None
        self.output_stream = f"{output_dir}/output.ts"
        self.output_file = f"{output_dir}/output.mp4"

    async def start(self, stream_url, title="Sandbox", delay=0):
        title = title.replace("'", "\\'")
        self.process = await asyncio.create_subprocess_shell(
            f"sleep {delay} && ffmpeg -reconnect 1 -i {stream_url} -c:v libx264 -preset fast -crf 23 "
            f"-c:a aac -b:a 128k -f mpegts -loglevel quiet - | tee {self.output_stream} | "
            f"ffplay -autoexit -i -loglevel quiet -window_title '{title}' -",
            preexec_fn=os.setsid,
            stdin=asyncio.subprocess.DEVNULL,
        )

    async def stop(self):
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            await self.process.wait()

    async def save_stream(self):
        process = await asyncio.create_subprocess_shell(
            f"ffmpeg -i {self.output_stream} -c:v copy -c:a copy -loglevel quiet {self.output_file}"
        )
        await process.wait()
        if process.returncode == 0:
            print(f"Stream saved successfully as {self.output_file}.")
        else:
            print(f"Failed to save the stream as {self.output_file}.")
