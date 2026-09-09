import json
import base64
import io
from litellm import completion
from PIL import Image


def Message(content, role="assistant"):
    return {"role": role, "content": content}


def Text(text):
    return {"type": "text", "text": text}


def parse_json(s):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        print(f"Error decoding JSON for tool call arguments: {s}")
        return None


class LiteLLMProvider:
    """
    Universal LLM provider using LiteLLM to support multiple model providers
    """

    def __init__(self, model, api_key=None, base_url=None):
        """
        Initialize with model name. LiteLLM handles provider detection automatically.

        Examples:
            - "gpt-4" or "gpt-3.5-turbo" for OpenAI
            - "claude-3-5-sonnet-20241022" for Anthropic
            - "mistral/mistral-large-latest" for Mistral
            - "gemini/gemini-pro" for Google
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        print(f"Using LiteLLM with model: {self.model}")

    def create_function_schema(self, definitions):
        """Convert function definitions to OpenAI-compatible tool schema"""
        functions = []

        for name, details in definitions.items():
            properties = {}
            required = []

            params = details.get("params", {})
            if not isinstance(params, dict):
                print(
                    f"Warning: Tool '{name}' has invalid params format. Expected dict."
                )
                continue

            for param_name, param_desc in params.items():
                properties[param_name] = {"type": "string", "description": param_desc}
                required.append(param_name)

            function_def = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": details["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
            functions.append(function_def)

        return functions

    def create_tool_call(self, name, parameters):
        """Represent a tool call as an object"""
        return {
            "type": "function",
            "name": name,
            "parameters": parameters,
        }

    def create_image_block(self, image_data: bytes):
        """Create an image block compatible with multiple providers"""
        image_type = "png"
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                image_type = img.format.lower()
        except Exception as e:
            print(f"Error detecting image type: {e}")

        encoded = base64.b64encode(image_data).decode("utf-8")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/{image_type};base64,{encoded}"},
        }

    def wrap_block(self, block):
        """Wrap a content block in text or image object"""
        if isinstance(block, bytes):
            return self.create_image_block(block)
        else:
            return Text(block)

    def transform_message(self, message):
        """Wrap all blocks in a given input message"""
        content = message["content"]
        if isinstance(content, list):
            wrapped_content = [self.wrap_block(block) for block in content]
            return {**message, "content": wrapped_content}
        else:
            return message

    def call(self, messages, functions=None, temperature=None, max_tokens=4096):
        """
        Make a call to any LLM provider through LiteLLM

        Args:
            messages: List of message dicts with 'role' and 'content'
            functions: Optional dict of function definitions
            temperature: Optional temperature parameter
            max_tokens: Maximum tokens in response

        Returns:
            If functions provided: (response_text, tool_calls)
            Otherwise: response_text
        """
        # Transform messages to wrap content blocks
        transformed_messages = [self.transform_message(msg) for msg in messages]

        # Build kwargs for LiteLLM
        kwargs = {
            "model": self.model,
            "messages": transformed_messages,
            "max_tokens": max_tokens,
        }

        if self.api_key:
            kwargs["api_key"] = self.api_key

        if self.base_url:
            kwargs["api_base"] = self.base_url

        if temperature is not None:
            kwargs["temperature"] = temperature

        # Add tools if provided
        if functions:
            kwargs["tools"] = self.create_function_schema(functions)
            kwargs["tool_choice"] = "auto"

        # Make the completion call
        try:
            response = completion(**kwargs)
        except Exception as e:
            raise Exception(f"Error calling model via LiteLLM: {e}")

        # Extract message from response
        message = response.choices[0].message

        # Handle function calling mode
        if functions:
            tool_calls = []

            # LiteLLM normalizes tool calls across providers
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    if hasattr(tool_call, "function"):
                        args = tool_call.function.arguments
                        # Parse if string
                        if isinstance(args, str):
                            args = parse_json(args)
                        if args is not None:
                            tool_calls.append(
                                self.create_tool_call(tool_call.function.name, args)
                            )

            # Get text content
            text_content = message.content if hasattr(message, "content") else None

            return text_content, tool_calls

        # Handle normal text response
        else:
            return message.content if hasattr(message, "content") else ""
