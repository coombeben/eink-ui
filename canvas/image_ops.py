"""
All functions for manipulating PIL Images
"""
import hashlib
from collections import OrderedDict
from io import BytesIO

import numpy as np
from PIL import Image

__all__ = ['get_vibrant_colour', 'luminance_transform', 'generate_vertical_gradient']


# Cache for theme colours
class ThemeColours:
    def __init__(self, max_size: int = 1024):
        self.max_size = max_size
        self._cache = OrderedDict()

    def _hash_image(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return hashlib.sha256(buffer.getvalue(), usedforsecurity=False).hexdigest()

    def get(self, image: Image.Image) -> tuple[int, int, int] | None:
        image_hash = self._hash_image(image)
        if hash in self._cache:
            self._cache.move_to_end(image_hash)
            return self._cache[image_hash]

        theme_colour = luminance_transform(get_vibrant_colour(image), threshold=3.)
        self._cache[image_hash] = theme_colour
        self._cache.move_to_end(image_hash)

        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

        return self._cache.get(image_hash)


def get_vibrant_colour(image: Image.Image, top_k: int = 100) -> tuple[int, int, int]:
    """
    Finds a vibrant background colour from an image

    Args:
        image: Input PIL Image
        top_k: Number of top candidates to average (higher = smoother, lower = more vibrant)

    Returns:
        RGB tuple
    """
    # Downsample for performance
    img = image.copy()
    img.thumbnail((128, 128))
    data = np.array(img) / 255.0
    pixels = data.reshape(-1, 3)

    # Convert to HSV for better colour filtering
    r, g, b = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    max_c = np.max(pixels, axis=1)
    min_c = np.min(pixels, axis=1)
    delta = max_c - min_c

    # Hue calculation
    hue = np.zeros_like(max_c)
    mask = delta != 0

    r_max = (max_c == r) & mask
    g_max = (max_c == g) & mask
    b_max = (max_c == b) & mask

    hue[r_max] = (60 * ((g[r_max] - b[r_max]) / delta[r_max]) + 360) % 360
    hue[g_max] = (60 * ((b[g_max] - r[g_max]) / delta[g_max]) + 120) % 360
    hue[b_max] = (60 * ((r[b_max] - g[b_max]) / delta[b_max]) + 240) % 360

    # Saturation
    saturation = np.divide(delta, max_c, out=np.zeros_like(delta), where=max_c != 0)

    # Value (brightness in HSV)
    value = max_c

    # Filter out achromatic colours (greys, whites, blacks)
    saturation_mask = saturation > 0.2

    # Avoid extreme darks and lights
    value_mask = (value > 0.15) & (value < 0.95)

    # Brown detection: Hue range: 0-40 degrees (red-orange-yellow)
    brown_mask = ~((hue < 40) & (saturation < 0.5))

    # Combine all filters
    valid_mask = saturation_mask & value_mask & brown_mask

    # Cascading fallback strategy for edge cases
    if not np.any(valid_mask):
        # Fallback 1: Relax saturation requirement
        valid_mask = (saturation > 0.1) & value_mask & brown_mask

    if not np.any(valid_mask):
        # Fallback 2: Accept browns but keep some saturation
        valid_mask = (saturation > 0.1) & value_mask

    if not np.any(valid_mask):
        # Fallback 3: Just take the most saturated pixels, ignore brightness
        valid_mask = saturation > 0.05

    if not np.any(valid_mask):
        # Fallback 4: Truly monochrome - pick mid-brightness greys
        valid_mask = (value > 0.3) & (value < 0.7)
        # If even this fails, just use all pixels (shouldn't happen)
        if not np.any(valid_mask):
            valid_mask = np.ones(len(pixels), dtype=bool)

    # Calculate vibrancy score only for valid pixels
    valid_pixels = pixels[valid_mask]
    valid_saturation = saturation[valid_mask]
    valid_value = value[valid_mask]

    # Vibrancy metric: combination of saturation and colour variance
    vibrancy = np.std(valid_pixels, axis=1)

    # Preference for mid-brightness colours (more visually appealing)
    brightness_pref = 1.0 - np.abs(valid_value - 0.5) * 1.5
    brightness_pref = np.clip(brightness_pref, 0.1, 1.0)

    # Final score: heavily weight saturation and vibrancy
    score = (valid_saturation ** 1.5) * (vibrancy ** 2) * brightness_pref

    # Get top K candidates and average them
    top_indices = np.argsort(score)[-top_k:]
    candidate_colours = valid_pixels[top_indices]

    # Weight by score when averaging
    top_scores = score[top_indices]
    weights = top_scores / np.sum(top_scores)
    avg_colour = np.average(candidate_colours, axis=0, weights=weights)

    avg_colour_rgb = (avg_colour * 255).astype(int).tolist()
    return tuple(avg_colour_rgb)


def luminance_transform(colour: tuple[int, int, int], threshold: float = 4.5) -> tuple[int, int, int]:
    """Applies a luminance transform to a colour to make white text stand out against it."""
    def srgb_to_linear(c: int) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def linear_to_srgb(c: float) -> int:
        c_srgb = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
        return max(0, min(255, int(round(c_srgb * 255))))

    r, g, b = colour

    # Convert sRGB to Linear RGB
    r_lin, g_lin, b_lin = srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b)

    # Calculate current relative luminance
    # Coefficients based on Rec. 709
    luminance = 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    # Calculate target background luminance for white text (L=1.0)
    max_lum = (1.05 / threshold) - 0.05

    # If already dark enough, return original; otherwise, scale down
    if luminance <= max_lum:
        return r, g, b

    scale = max_lum / luminance
    return (
        linear_to_srgb(r_lin * scale),
        linear_to_srgb(g_lin * scale),
        linear_to_srgb(b_lin * scale)
    )


def generate_vertical_gradient(top_color, shape, power=1.5) -> Image.Image:
    """
    Creates a vertical gradient from top_color to black using a power curve
    to avoid the 'grey dead zone' in the middle.

    :param top_color: Tuple of (R, G, B)
    :param shape: Tuple of (width, height)
    :param power: Higher values (e.g. 1.5-2.0) keep the colour 'pure' longer.
    """
    width, height = shape

    # 1. Create a 1D ramp (1.0 to 0.0)
    # Applying a power curve prevents the colour from washing out too early
    ramp = np.linspace(1.0, 0.0, height) ** power
    ramp = ramp.reshape(height, 1, 1)

    # 2. Convert colour to array and normalise to 0.0-1.0 for maths
    color_array = np.array(top_color) / 255.0

    # 3. Multiply and broadcast
    gradient_data = ramp * color_array * np.ones((1, width, 1))

    # 4. Convert back to 0-255 uint8
    return Image.fromarray((gradient_data * 255).astype(np.uint8))
