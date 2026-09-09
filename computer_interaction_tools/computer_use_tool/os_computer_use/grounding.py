from PIL import ImageDraw
import re


def draw_big_dot(image, coordinates, color="red", radius=12):
    draw = ImageDraw.Draw(image)
    x, y = coordinates
    bounding_box = [x - radius, y - radius, x + radius, y + radius]
    draw.ellipse(bounding_box, fill=color, outline=color)
    return image


def extract_bbox_midpoint(bbox_response, screen_width=None, screen_height=None):
    """Extract bounding box coordinates from grounding model response.

    Args:
        bbox_response: The response text from the grounding model
        screen_width: Optional screen width to filter out dimension-like numbers
        screen_height: Optional screen height to filter out dimension-like numbers
    """
    if not bbox_response or not isinstance(bbox_response, str):
        return None

    print(bbox_response)

    match = re.search(r"<\|box_start\|>(.*?)<\|box_end\|>", bbox_response)
    inner_text = match.group(1) if match else bbox_response

    try:
        numbers = [float(num) for num in re.findall(r"\d+\.\d+|\d+", inner_text)]

        if len(numbers) == 2:
            x, y = numbers[0], numbers[1]
            # If we have screen dimensions, filter out numbers that match them
            if screen_width and screen_height:
                if (x == screen_width and y == screen_height) or (
                    x == screen_width - 1 and y == screen_height - 1
                ):
                    return None  # These look like screen dimensions, not coordinates
            return x, y

        elif len(numbers) >= 4:
            # Calculate midpoint from bounding box [x1, y1, x2, y2]
            x1, y1, x2, y2 = numbers[0], numbers[1], numbers[2], numbers[3]
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2

            # Filter out if it looks like screen dimensions
            if screen_width and screen_height:
                if (center_x == screen_width and center_y == screen_height) or (
                    center_x == screen_width - 1 and center_y == screen_height - 1
                ):
                    return None
            return center_x, center_y
        else:
            return None
    except (ValueError, TypeError):
        return None
