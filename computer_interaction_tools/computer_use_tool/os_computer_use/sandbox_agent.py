import os
import tempfile
import io
import json
import re

from PIL import Image

from os_computer_use.config import vision_model, action_model, grounding_model
from os_computer_use.llm_provider import Message
from os_computer_use.logging import logger
from os_computer_use.grounding import draw_big_dot


TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50
DEFAULT_SYSTEM_PROMPT = "You are an AI assistant with computer use abilities."

tools = {
    "stop": {
        "description": "Indicate that the task has been completed.",
        "params": {},
    }
}


class SandboxAgent:
    def __init__(self, sandbox, output_dir=".", save_logs=True, system_prompt=None):
        super().__init__()
        self.messages = []  # Agent memory
        self.sandbox = sandbox  # Docker-backed sandbox
        self.latest_screenshot = None  # Most recent PNG file path
        self.latest_screenshot_bytes = None  # Most recent PNG bytes
        self.image_counter = 0  # Current screenshot number
        # Store screenshots under the provided output_dir to honor MCP_SAVEFILES_PATH
        os.makedirs(output_dir, exist_ok=True)
        self.tmp_dir = tempfile.mkdtemp(dir=output_dir)  # Folder to store screenshots
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        # Set the log file location
        if save_logs:
            logger.log_file = f"{output_dir}/log.html"

        print("The agent will use the following actions:")
        for action, details in tools.items():
            param_str = ", ".join(details.get("params").keys())
            print(f"- {action}({param_str})")

    def call_function(self, name, arguments):

        func_impl = getattr(self, name.lower()) if name.lower() in tools else None
        if func_impl:
            try:
                # Handle case where arguments might be a string (JSON) or None
                if arguments is None:
                    arguments = {}
                elif isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        # If it's not valid JSON, treat it as a single string argument
                        # This handles cases where the model returns a simple string
                        arguments = (
                            {"query": arguments}
                            if name.lower() in ["click", "double_click", "right_click"]
                            else {}
                        )
                elif not isinstance(arguments, dict):
                    # Convert other types to dict if possible
                    arguments = (
                        {"query": str(arguments)}
                        if name.lower() in ["click", "double_click", "right_click"]
                        else {}
                    )

                result = func_impl(**arguments) if arguments else func_impl()
                return result
            except Exception as e:
                import traceback

                error_trace = traceback.format_exc()
                logger.log(
                    f"Error executing function {name}: {str(e)}\n{error_trace}", "red"
                )
                return f"Error executing function: {str(e)}"
        else:
            return "Function not implemented."

    def tool(description, params):
        def decorator(func):
            tools[func.__name__] = {"description": description, "params": params}
            return func

        return decorator

    def save_image(self, image, prefix="image"):
        self.image_counter += 1
        filename = f"{prefix}_{self.image_counter}.png"
        filepath = os.path.join(self.tmp_dir, filename)
        if isinstance(image, Image.Image):
            image.save(filepath)
        else:
            with open(filepath, "wb") as f:
                f.write(image)
        return filepath

    def screenshot(self):
        file = self.sandbox.screenshot()
        filename = self.save_image(file, "screenshot")
        logger.log(f"screenshot {filename}", "gray")
        # Store both the filename (for drawing dots) and the bytes (for grounding model)
        self.latest_screenshot = filename
        self.latest_screenshot_bytes = file  # Store the raw bytes
        return file

    @tool(
        description="Run a shell command and return the result.",
        params={"command": "Shell command to run synchronously"},
    )
    def run_command(self, command):
        result = self.sandbox.commands.run(command, timeout=5)
        stdout, stderr = result.stdout, result.stderr
        if stdout and stderr:
            return stdout + "\n" + stderr
        elif stdout or stderr:
            return stdout + stderr
        else:
            return "The command finished running."

    @tool(
        description="Run a shell command in the background.",
        params={"command": "Shell command to run asynchronously"},
    )
    def run_background_command(self, command):
        self.sandbox.commands.run(command, background=True)
        return "The command has been started."

    @tool(
        description="Send a key or combination of keys to the system.",
        params={"name": "Key or combination (e.g. 'Return', 'Ctl-C')"},
    )
    def send_key(self, name):
        self.sandbox.press(name)
        return "The key has been pressed."

    @tool(
        description="Type a specified text into the system.",
        params={"text": "Text to type"},
    )
    def type_text(self, text):
        self.sandbox.write(
            text, chunk_size=TYPING_GROUP_SIZE, delay_in_ms=TYPING_DELAY_MS
        )
        return "The text has been typed."

    def click_element(self, query, click_command, action_name="click"):
        """Base method for all click operations"""
        self.screenshot()

        # Format the call correctly based on the grounding model type
        grounding_model_type = str(type(grounding_model))
        if hasattr(grounding_model, "call") and (
            "OSAtlasProvider" in grounding_model_type
            or "ShowUIProvider" in grounding_model_type
        ):
            # OSAtlasProvider/Florence2Provider/Qwen3VLProvider signature - pass bytes, not file path
            if self.latest_screenshot_bytes is None:
                return (
                    f"Error: Screenshot bytes not available. Cannot locate '{query}'."
                )
            position = grounding_model.call(query, self.latest_screenshot_bytes)
        else:
            # OpenAIProvider/other LLM providers signature
            from os_computer_use.llm_provider import Message

            # Ensure we have the bytes (should be set by screenshot() above)
            if self.latest_screenshot_bytes is None:
                return (
                    f"Error: Screenshot bytes not available. Cannot locate '{query}'."
                )

            # Get screenshot dimensions for validation
            # Image is already imported at module level
            img = Image.open(io.BytesIO(self.latest_screenshot_bytes))
            screen_width, screen_height = img.size

            # Retry logic: try up to 3 times with different prompt variations
            max_retries = 3
            position = None

            prompt_variations = [
                # Variation 1: Very specific and detailed
                f"""You are a UI element localization expert. Find the exact center coordinates of the UI element described as "{query}" in this {screen_width}×{screen_height} pixel screenshot.

INSTRUCTIONS:
1. Scan the entire image systematically from top-left to bottom-right
2. Look for text, buttons, links, icons, or interactive elements matching "{query}"
3. Match partial text: if query is "Skip", look for "Skip", "Skip this", "Skip step", etc.
4. Identify the CENTER point of the clickable/interactive area (not edges)
5. If multiple matches exist, choose the most prominent, visible, or relevant one

CRITICAL: Return ONLY valid JSON with integer coordinates:
{{"x": <integer>, "y": <integer>}}

Constraints: x must be 0-{screen_width}, y must be 0-{screen_height}. Both must be integers.
No explanations, no markdown, just the JSON object.""",
                # Variation 2: More direct
                f"""Locate "{query}" in this {screen_width}×{screen_height} screenshot. Return the center coordinates as JSON: {{"x": <int>, "y": <int>}}. Coordinates must be within 0-{screen_width} for x and 0-{screen_height} for y.""",
                # Variation 3: Step-by-step
                f"""Step 1: Find the UI element that matches "{query}" in this {screen_width}×{screen_height} screenshot.
Step 2: Identify the center point of that element.
Step 3: Return ONLY: {{"x": <integer>, "y": <integer>}}
x range: 0-{screen_width}, y range: 0-{screen_height}.""",
            ]

            for attempt in range(max_retries):
                try:
                    # Use a system message to set context, then the user message with image
                    prompt_text = prompt_variations[attempt % len(prompt_variations)]
                    messages = [
                        Message(
                            "You are an expert at locating UI elements in screenshots. You analyze images carefully and return precise pixel coordinates as JSON. You are accurate and reliable.",
                            role="system",
                        ),
                        Message(
                            [
                                prompt_text,
                                self.latest_screenshot_bytes,
                            ],
                            role="user",
                        ),
                    ]
                    # Call without functions parameter for grounding (returns just content string)
                    response_content = grounding_model.call(
                        messages, functions=None, temperature=0.1
                    )

                    # response_content is a string when functions=None
                    # Try multiple JSON extraction patterns
                    json_patterns = [
                        r'\{[^}]*"x"\s*:\s*\d+[^}]*"y"\s*:\s*\d+[^}]*\}',  # Flexible spacing
                        r'\{"x":\s*\d+,\s*"y":\s*\d+\}',  # Strict format
                        r'\{[^}]*"x"[^}]*"y"[^}]*\}',  # Original pattern
                    ]

                    position = None
                    for pattern in json_patterns:
                        json_match = re.search(
                            pattern, str(response_content), re.IGNORECASE
                        )
                        if json_match:
                            try:
                                coords = json.loads(json_match.group())
                                x = float(coords.get("x", coords.get("X", 0)))
                                y = float(coords.get("y", coords.get("Y", 0)))
                                # Validate coordinates are within screen bounds
                                if 0 <= x <= screen_width and 0 <= y <= screen_height:
                                    position = (int(x), int(y))
                                    logger.log(
                                        f"Grounding found coordinates (attempt {attempt + 1}): {position} for '{query}'",
                                        "gray",
                                    )
                                    break
                                else:
                                    logger.log(
                                        f"Warning: Coordinates {x},{y} out of bounds ({screen_width}x{screen_height})",
                                        "yellow",
                                    )
                            except (json.JSONDecodeError, ValueError, TypeError):
                                continue

                    # Fallback: try to find two numbers in the response
                    if position is None:
                        numbers = re.findall(r"\d+", str(response_content))
                        if len(numbers) >= 2:
                            x, y = int(numbers[0]), int(numbers[1])
                            if 0 <= x <= screen_width and 0 <= y <= screen_height:
                                position = (x, y)
                                logger.log(
                                    f"Grounding found coordinates (fallback, attempt {attempt + 1}): {position} for '{query}'",
                                    "gray",
                                )

                    # If we got a valid position, break out of retry loop
                    if position is not None:
                        break
                    else:
                        logger.log(
                            f"Grounding attempt {attempt + 1} failed, retrying with different prompt...",
                            "yellow",
                        )
                except Exception as e:
                    logger.log(
                        f"Error in grounding attempt {attempt + 1}: {str(e)}", "red"
                    )
                    if attempt < max_retries - 1:
                        logger.log("Retrying...", "yellow")
                    continue

        # Validate that position is a tuple of two numbers
        if position is None:
            return f"Error: Could not locate '{query}' on the screen. The element may not be visible or the grounding model failed."

        if not isinstance(position, (tuple, list)) or len(position) != 2:
            return f"Error: Grounding model returned invalid position format: {position}. Expected (x, y) coordinates."

        try:
            x, y = float(position[0]), float(position[1])
        except (ValueError, TypeError) as e:
            return f"Error: Could not parse coordinates from grounding model response: {position}. {str(e)}"

        dot_image = draw_big_dot(Image.open(self.latest_screenshot), (x, y))
        filepath = self.save_image(dot_image, "location")
        logger.log(f"{action_name} {filepath})", "gray")

        self.sandbox.move_mouse(int(x), int(y))
        click_command()
        return f"The mouse has {action_name}ed at ({int(x)}, {int(y)})."

    @tool(
        description="Click on a specified UI element.",
        params={
            "query": "Item or UI element on the screen to click with proper description"
        },
    )
    def click(self, query):
        return self.click_element(query, self.sandbox.left_click)

    @tool(
        description="Double click on a specified UI element.",
        params={
            "query": "Item or UI element on the screen to double click with proper description"
        },
    )
    def double_click(self, query):
        return self.click_element(query, self.sandbox.double_click, "double click")

    @tool(
        description="Right click on a specified UI element.",
        params={
            "query": "Item or UI element on the screen to right click with proper description"
        },
    )
    def right_click(self, query):
        return self.click_element(query, self.sandbox.right_click, "right click")

    @tool(
        description="Scroll up by a specified amount.",
        params={
            "query": "Item or UI element on the screen to scroll up with proper description",
            "amount": "Amount to scroll up (default is 1)",
        },
    )
    def scroll_up(self, query, amount: int = 1):
        return self.click_element(
            query,
            lambda: self.sandbox.scroll_up(amount),
            "scroll up",
        )

    @tool(
        description="Scroll down by a specified amount.",
        params={
            "query": "Item or UI element on the screen to scroll down with proper description",
            "amount": "Amount to scroll down (default is 1)",
        },
    )
    def scroll_down(self, query, amount: int = 1):
        return self.click_element(
            query,
            lambda: self.sandbox.scroll_down(amount),
            "scroll down",
        )

    @tool(
        description="Move the mouse to specified (x, y) coordinates.",
        params={
            "x": "X coordinate to move the mouse to",
            "y": "Y coordinate to move the mouse to",
        },
    )
    def move_mouse(self, x: int, y: int):
        """Move the mouse to specified (x, y) coordinates."""
        self.sandbox.move_mouse(x, y)
        return f"The mouse has been moved to ({x}, {y})."

    def append_screenshot(self):
        return vision_model.call(
            [
                *self.messages,
                Message(
                    [
                        self.screenshot(),
                        "This image shows the current display of the computer. Please respond in the following format:\n"
                        "The objective is: [put the objective here]\n"
                        "On the screen, I see: [an extensive list of everything that might be relevant to the objective including windows, icons, menus, apps, and UI elements]\n"
                        "This means the objective is: [complete|not complete]\n\n"
                        "(Only continue if the objective is not complete.)\n"
                        "The next step is to [click|type|run the shell command] [put the next single step here] in order to [put what you expect to happen here].",
                    ],
                    role="user",
                ),
            ]
        )

    def run(self, instruction):

        self.messages.append(Message(f"OBJECTIVE: {instruction}"))
        logger.log(f"USER: {instruction}", print=False)

        should_continue = True
        while should_continue:
            # Stop the sandbox from timing out
            self.sandbox.set_timeout(60)

            content, tool_calls = action_model.call(
                [
                    Message(
                        self.system_prompt,
                        role="system",
                    ),
                    *self.messages,
                    Message(
                        logger.log(f"THOUGHT: {self.append_screenshot()}", "green")
                    ),
                    Message(
                        "I will now use tool calls to take these actions, or use the stop command if the objective is complete.",
                    ),
                ],
                tools,
            )

            if content:
                self.messages.append(Message(logger.log(f"THOUGHT: {content}", "blue")))

            should_continue = False
            for tool_call in tool_calls:
                # Handle case where tool_call might be a string or dict
                if isinstance(tool_call, str):
                    try:
                        tool_call = json.loads(tool_call)
                    except json.JSONDecodeError:
                        logger.log(
                            f"Error: Could not parse tool_call as JSON: {tool_call}",
                            "red",
                        )
                        continue

                if not isinstance(tool_call, dict):
                    logger.log(
                        f"Error: tool_call is not a dict: {type(tool_call)} - {tool_call}",
                        "red",
                    )
                    continue

                name = tool_call.get("name")
                parameters = tool_call.get("parameters")

                # Parse parameters if it's a JSON string
                if isinstance(parameters, str):
                    try:
                        parameters = json.loads(parameters)
                    except json.JSONDecodeError:
                        # Keep as string if not valid JSON
                        pass

                should_continue = name != "stop"
                if not should_continue:
                    break
                # Print the tool-call in an easily readable format
                logger.log(f"ACTION: {name} {str(parameters)}", "red")
                # Write the tool-call to the message history using the same format used by the model
                self.messages.append(Message(json.dumps(tool_call)))
                result = self.call_function(name, parameters)

                self.messages.append(
                    Message(logger.log(f"OBSERVATION: {result}", "yellow"))
                )
