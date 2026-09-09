import ast
import os
import numpy as np
from PIL import Image
from gradio_client import Client, handle_file
from os_computer_use.logging import logger

SHOWUI_HUGGINGFACE_SOURCE = "AI-DrivenTesting/ShowUI"
SHOWUI_HUGGINGFACE_MODEL = "showlab/ShowUI-2B"
SHOWUI_HUGGINGFACE_API = "/on_submit"


class ShowUIProvider:
    """
    The ShowUI provider is used to make calls to ShowUI.
    """

    def __init__(self):
        try:
            self.client = Client(SHOWUI_HUGGINGFACE_SOURCE)
            logger.log(
                f"Successfully connected to ShowUI space: {SHOWUI_HUGGINGFACE_SOURCE}",
                "gray",
            )
        except Exception as e:
            logger.log(f"Error connecting to ShowUI space: {str(e)}", "yellow")
            self.client = None

    def extract_norm_point(self, response, image_url):
        try:
            if isinstance(image_url, str):
                image = Image.open(image_url)
            else:
                image = Image.fromarray(np.uint8(image_url))

            # Try to parse the response as a point
            point = ast.literal_eval(response)
            if len(point) == 2:
                x, y = point[0] * image.width, point[1] * image.height
                logger.log(f"ShowUI found position: ({x}, {y})", "gray")
                return x, y
            else:
                logger.log(f"ShowUI returned invalid point format: {point}", "yellow")
                return None
        except Exception as e:
            logger.log(
                f"Error extracting point from ShowUI response: {str(e)}, response: {response}",
                "yellow",
            )
            return None

    def call(self, prompt, image_data):
        if self.client is None:
            logger.log("ShowUI client not initialized", "yellow")
            return None

        tmp_path = None
        try:
            # Ensure image_data is bytes or file path
            if isinstance(image_data, str):
                # If it's a file path, use it directly with handle_file
                image_input = handle_file(image_data)
            elif isinstance(image_data, bytes):
                # If it's bytes, save to temp file first
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    tmp.write(image_data)
                    tmp_path = tmp.name
                image_input = handle_file(tmp_path)
            else:
                logger.log(
                    f"Error: image_data must be bytes or file path, got {type(image_data)}",
                    "red",
                )
                return None

            logger.log(f"Calling ShowUI with query: '{prompt}'", "gray")
            result = self.client.predict(
                image=image_input,
                query=prompt,
                iterations=1,
                is_example_image="False",
                api_name=SHOWUI_HUGGINGFACE_API,
            )

            # Log the raw result for debugging
            logger.log(f"ShowUI raw result: {result}", "gray")

            # Check if result has expected structure
            if not result or len(result) < 2:
                logger.log(
                    f"Error: ShowUI returned unexpected result format: {result}", "red"
                )
                return None

            pred = result[1]

            # Check if result[0] exists and has the expected structure
            if not result[0] or not isinstance(result[0], list) or len(result[0]) == 0:
                logger.log(
                    f"Error: ShowUI result[0] has unexpected format: {result[0]}", "red"
                )
                return None

            if not isinstance(result[0][0], dict) or "image" not in result[0][0]:
                logger.log(
                    f"Error: ShowUI result[0][0] missing 'image' key: {result[0][0]}",
                    "red",
                )
                return None

            img_url = result[0][0]["image"]
            position = self.extract_norm_point(pred, img_url)

            if position:
                logger.log(f"ShowUI found position: {position} for '{prompt}'", "gray")

            return position
        except Exception as e:
            logger.log(f"Error calling ShowUI: {str(e)}", "red")
            import traceback

            logger.log(f"Traceback: {traceback.format_exc()}", "red")
            return None
        finally:
            # Clean up temp file after API call completes
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass


if __name__ == "__main__":
    showuiprovider = ShowUIProvider()
    img_url = "/home/qinghong/example/demo/chrome.png"
    query = "search box"
    result = showuiprovider.call(query, img_url)
    print(result)
