import colorsys
import math
import copy
import random
from typing import Tuple, List

max_angle = 150
min_angle = 2

white_point = (0.3127, 0.3290)

def get_next_smart_random_color(current: Tuple[float, float], options: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(options) == 1:
        return options[0]

    valid_end_colors = []

    for color in options:
        # Calculate the vectors originating from the current color and the target color to the white point
        vector1 = (current[0] - white_point[0], current[1] - white_point[1])
        vector2 = (color[0] - white_point[0], color[1] - white_point[1])

        # Calculate the lengths of the vectors for normalization
        length1 = math.sqrt(vector1[0] ** 2 + vector1[1] ** 2)
        length2 = math.sqrt(vector2[0] ** 2 + vector2[1] ** 2)

        # Calculate the dot product of normalized vectors to find the cosine of the angle
        dot_product = (vector1[0] / length1) * (vector2[0] / length2) + (vector1[1] / length1) * (vector2[1] / length2)

        # Clip the dot product to the range [-1, 1]
        dot_product = max(-1.0, min(1.0, dot_product))

        angle = math.degrees(math.acos(dot_product))

        # The point of all of this is to not have lights flash bright white during transitions between colors
        # that are at opposing ends of the color space. Thanks, math
        if min_angle < angle < max_angle:
            valid_end_colors.append(color)

    if valid_end_colors:
        selected_end_color = random.choice(valid_end_colors)

        return selected_end_color
    else:
        # If no valid transition is found, return any random color
        return random.choice(options)

def get_next_color(idx: int, options: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(options) == 1:
        return options[0]

    wrapped_idx = idx % len(options)
    next_color = options[wrapped_idx]

    return next_color

def get_random_color(options: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(options) == 1:
        return options[0]

    random_color = random.choice(options)

    return random_color

def get_randomized_colors(options: List[Tuple[float, float]], total: int) -> List[Tuple[float, float]]:
    color_sets_required = math.ceil(total/len(options))
    colors = []

    for _ in range(color_sets_required):
        color_set = copy.copy(options)
        random.shuffle(color_set)
        colors.extend(color_set)

    colors = colors[:total]

    return colors

def adjust_saturation(colors: List[Tuple[float, float]], amount) -> List[Tuple[float, float]]:
    """Make the colors of a preset more vivid (amount > 0) or paler (amount < 0), hue unchanged.

    amount is -100..100 (percent). 100 gives fully saturated colors, -100 white. Near-white colors
    (white tones of a preset) are not made more colorful, their hue is not meaningful.
    """
    if not amount:
        return colors
    from homeassistant.util import color as color_util

    k = max(-100.0, min(100.0, float(amount))) / 100
    adjusted = []
    for x, y in colors:
        r, g, b = color_util.color_xy_to_RGB(x, y)
        hue, sat, _val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if k > 0:
            if sat < 0.15:
                adjusted.append((x, y))
                continue
            sat = sat + (1 - sat) * k
        else:
            sat = sat * (1 + k)
        r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
        nx, ny = color_util.color_RGB_to_xy(round(r * 255), round(g * 255), round(b * 255))
        adjusted.append((round(nx, 4), round(ny, 4)))
    return adjusted
