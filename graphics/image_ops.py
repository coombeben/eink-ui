"""
All functions for manipulating PIL Images

As the theme colour is calculated using a KMeans clustering algorithm,
it is cached for performance reasons.
"""
import hashlib

import numpy as np
from diskcache import Cache
from PIL import Image
from sklearn.cluster import KMeans

__all__ = ['ThemeColours', 'generate_vertical_gradient']


# Cache for theme colours
class ThemeColours:
    def __init__(self, size_limit: int = 1e7, eviction_policy: str = 'least-recently-used', **kwargs):
        """Cache for theme colours.

        Args:
            size_limit: The max size (on disk) of the cache in bytes
            eviction_policy: The eviction policy to use. See
                https://grantjenks.com/docs/diskcache/tutorial.html#tutorial-eviction-policies
        """
        self._cache = Cache(
            'theme-colours',
            size_limit=size_limit,
            eviction_policy=eviction_policy,
            **kwargs
        )

    def _hash_image(self, image: Image.Image) -> str:
        """Returns the hash of a PIL image."""
        img = image.resize((64, 64), resample=Image.Resampling.NEAREST)
        return hashlib.sha256(img.tobytes()).hexdigest()

    def get(self, image: Image.Image) -> tuple[int, int, int]:
        """Simple LRU cache implementation"""
        image_hash = self._hash_image(image)
        cached_theme_colour = self._cache.get(image_hash)
        if cached_theme_colour is not None:
            return cached_theme_colour

        theme_colour = get_theme_colour(image, min_contrast=3.)  # Expensive!
        self._cache[image_hash] = theme_colour
        return theme_colour

    def close(self) -> None:
        """Closes the cache."""
        self._cache.close()


def rgb_to_lab(rgb_pixels: np.ndarray) -> np.ndarray:
    """
    Convert an array of RGB pixels (0..1) to CIELAB.
    Input shape: (N, 3), Output shape: (N, 3)
    """
    # 1. RGB to XYZ
    # Inverse sRGB Gamma correction
    mask = rgb_pixels > 0.04045
    rgb_pixels[mask] = ((rgb_pixels[mask] + 0.055) / 1.055) ** 2.4
    rgb_pixels[~mask] /= 12.92

    # sRGB to XYZ Matrix
    M = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = np.dot(rgb_pixels, M.T)

    # 2. XYZ to Lab
    # Normalise to D65 White Point
    xyz[:, 0] /= 0.95047
    xyz[:, 1] /= 1.00000
    xyz[:, 2] /= 1.08883

    mask = xyz > 0.008856
    xyz[mask] = xyz[mask] ** (1 / 3)
    xyz[~mask] = 7.787 * xyz[~mask] + 16 / 116

    lab = np.zeros_like(xyz)
    lab[:, 0] = 116 * xyz[:, 1] - 16  # L
    lab[:, 1] = 500 * (xyz[:, 0] - xyz[:, 1])  # a
    lab[:, 2] = 200 * (xyz[:, 1] - xyz[:, 2])  # b
    return lab


def lab_to_rgb(lab_pixels: np.ndarray) -> np.ndarray:
    """
    Convert an array of CIELAB pixels to RGB (0..1).
    Input shape: (N, 3), Output shape: (N, 3)
    """
    # 1. Lab to XYZ
    y = (lab_pixels[:, 0] + 16) / 116
    x = lab_pixels[:, 1] / 500 + y
    z = y - lab_pixels[:, 2] / 200

    xyz = np.stack([x, y, z], axis=1)

    mask = xyz > 0.20689
    xyz[mask] = xyz[mask] ** 3
    xyz[~mask] = (xyz[~mask] - 16 / 116) / 7.787

    # Denormalize D65
    xyz[:, 0] *= 0.95047
    xyz[:, 1] *= 1.00000
    xyz[:, 2] *= 1.08883

    # 2. XYZ to RGB
    M_inv = np.array([[3.2406, -1.5372, -0.4986],
                      [-0.9689, 1.8758, 0.0415],
                      [0.0557, -0.2040, 1.0570]])
    rgb = np.dot(xyz, M_inv.T)

    # Gamma correction
    mask = rgb > 0.0031308
    rgb[mask] = 1.055 * (rgb[mask] ** (1 / 2.4)) - 0.055
    rgb[~mask] *= 12.92

    return np.clip(rgb, 0, 1)


def contrast_ratio_with_white(rgb: np.ndarray) -> float:
    """Returns the contrast ratio of the given RGB tuple with white."""
    def srgb_channel_to_linear(c):
        # c in [0,1]
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

    # Relative luminance
    r, g, b = rgb
    rl, gl, bl = srgb_channel_to_linear(np.array([r, g, b]))
    luminance = 0.2126 * rl + 0.7152 * gl + 0.0722 * bl

    return (1.0 + 0.05) / (luminance + 0.05)


def ensure_white_text_contrast_lab(
        lab: np.ndarray, min_contrast: float = 3.0, step: float = 1.0,
        min_luminance: float = 0.0) -> np.ndarray:
    """
    Darken by reducing L* until contrast with white meets threshold.
    Keeps a*, b* to preserve hue/chroma as much as possible.
    """
    luminance, a, b = lab
    luminance = float(luminance)
    for _ in range(200):  # enough to walk L* downward
        rgb = np.clip(lab_to_rgb(np.array([[luminance, a, b]]))[0], 0.0, 1.0)
        if contrast_ratio_with_white(rgb) >= min_contrast:
            return np.array([luminance, a, b], dtype=float)
        luminance = max(min_luminance, luminance - step)
        if luminance <= min_luminance:
            break
    return np.array([luminance, a, b], dtype=float)


def score_colour(lab: np.ndarray, prevalence: float) -> float:
    """
    Compute a perceptual suitability score for a candidate theme colour.

    The intent of this function is to favour colours that are visually interesting,
    commonly occurring, and suitable for use as a background colour. This uses 3
    different weighting factors:
    1. Prevalence weighting: More frequent colours are more important.
    2. Chroma weighting: Colours with a high chroma are preferred.
    3. Lightness weighting: Colours close to white or black are downweighted.
    """
    lightness, a, b = lab
    chroma = float(np.sqrt(a * a + b * b))  # chroma in Lab

    # Lightness gating: avoid backgrounds too close to white (hard to contrast)
    # and too close to black (often looks dull as a "theme" background).
    # But don't forbid them—just downweight.
    lightness_penalty = 1.0
    if lightness > 85:
        lightness_penalty *= max(0.25, (100 - lightness) / 15.)
    elif lightness < 20:
        lightness_penalty *= max(0.1, lightness / 20.)

    # "Interesting" penalty for near-neutral colours (low chroma).
    # Soft penalty: if image is muted, we still pick the best available.
    chroma_weight = np.clip(chroma / 40.0, 0.05, 1.5)

    # Prevalence: strongly matters, but don't let it dominate completely.
    prevalence_weight = np.sqrt(prevalence)

    score = prevalence_weight * chroma_weight * lightness_penalty
    return score


def get_theme_colour(
    image: Image.Image,
    n_clusters: int = 8,
    min_contrast: float = 3.0,
    thumb_size=(128, 128),
) -> tuple[int, int, int]:
    """
    Returns an sRGB tuple (R,G,B) 0..255.
    Picks a prevalent, chromatic Lab cluster, then darkens to meet contrast with white text.
    """
    img = image.convert("RGB").copy()
    img.thumbnail(thumb_size)

    rgb_pixels = (np.asarray(img).reshape(-1, 3).astype(np.float32) / 255.0)
    if len(rgb_pixels) == 0:
        return 0, 0, 0

    lab_pixels = rgb_to_lab(rgb_pixels)

    # KMeans can fail if n_clusters > unique colours (common in flat images)
    # So clamp clusters to number of unique pixels (or at least 1).
    unique_count = len(np.unique(rgb_pixels, axis=0))
    k = max(1, min(n_clusters, unique_count))

    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(lab_pixels)
    centres = kmeans.cluster_centers_  # Lab
    counts = np.bincount(labels, minlength=k)
    prevalence_scores = counts / counts.sum()

    # Score each cluster
    scores = []
    for centre, prevalence in zip(centres, prevalence_scores):
        scores.append(score_colour(centre, prevalence))

    best = int(np.argmax(scores))
    best_lab = centres[best].astype(float)

    # If everything is basically monochrome (very low chroma across centres),
    # choose a cluster that is actually visible against a black gradient.
    chromas = np.sqrt(centres[:, 1] ** 2 + centres[:, 2] ** 2)
    if float(np.max(chromas)) < 8.0:
        # Filter for clusters that aren't "too dark" (e.g. L > 15)
        # Using 15-20 ensures we don't pick the 'void' in a black photo.
        visible_mask = centres[:, 0] > 15

        if np.any(visible_mask):
            # Of the visible clusters, pick the most prevalent one.
            # This ensures we pick the "main" grey/white rather than a tiny speck.
            visible_indices = np.where(visible_mask)[0]
            best = visible_indices[np.argmax(prevalence_scores[visible_indices])]
        else:
            # If the entire image is ultra-dark (all L <= 15),
            # pick the lightest available cluster so it's at least a dark grey.
            best = int(np.argmax(centres[:, 0]))

        best_lab = centres[best].astype(float)

    # Enforce contrast by darkening L* (keeping a*, b*)
    best_lab = ensure_white_text_contrast_lab(best_lab, min_contrast=min_contrast)

    # Convert to RGB
    rgb01 = np.clip(lab_to_rgb(best_lab[None, :])[0], 0.0, 1.0)
    rgb255 = (rgb01 * 255.0 + 0.5).astype(np.int32)
    return int(rgb255[0]), int(rgb255[1]), int(rgb255[2])


def generate_vertical_gradient(top_colour: tuple, shape: tuple, power: float = 1.5) -> Image.Image:
    """
    Creates a vertical gradient from top_colour to black using a power curve
    to avoid the 'grey dead zone' in the middle.

    :param top_colour: Tuple of (R, G, B)
    :param shape: Tuple of (width, height)
    :param power: Higher values (e.g. 1.5-2.0) keep the colour 'pure' longer.
    """
    width, height = shape

    # Create a 1D ramp (1.0 to 0.0)
    # Applying a power curve prevents the colour from washing out too early
    ramp = np.linspace(1.0, 0.0, height) ** power
    ramp = ramp.reshape(height, 1, 1)

    # Convert colour to array and normalise to 0.0-1.0 for maths
    color_array = np.array(top_colour) / 255.0

    # Multiply and broadcast
    gradient_data = ramp * color_array * np.ones((1, width, 1))

    # Convert back to 0-255 uint8
    return Image.fromarray((gradient_data * 255).astype(np.uint8))
