"""
diskcache wrapper for theme colours
"""
import hashlib

from PIL import Image
from diskcache import Cache

from .image_ops import get_theme_colour


class ThemeCache:
    def __init__(self, directory: str = 'theme-colours', size_limit: int = 10_000_000,
                 eviction_policy: str = 'least-recently-used', **kwargs):
        """Cache for theme colours.

        Args:
            directory: The directory to store the cache in.
            size_limit: The max size (on disk) of the cache in bytes.
            eviction_policy: The eviction policy to use. See
                https://grantjenks.com/docs/diskcache/tutorial.html#tutorial-eviction-policies
        """
        self._cache = Cache(
            directory,
            size_limit=size_limit,
            eviction_policy=eviction_policy,
            **kwargs
        )

    @staticmethod
    def _hash_image(image: Image.Image) -> str:
        """Returns the hash of a PIL image."""
        img = image.resize((64, 64), resample=Image.Resampling.NEAREST)
        return hashlib.sha256(img.tobytes()).hexdigest()

    def get(self, image: Image.Image) -> tuple[int, int, int]:
        """Simple LRU cache implementation"""
        image_hash = self._hash_image(image)
        cached_theme_colour = self._cache.get(image_hash)
        if cached_theme_colour is not None:
            return cached_theme_colour

        theme_colour = get_theme_colour(image, min_contrast=3.)
        self._cache[image_hash] = theme_colour
        return theme_colour

    def close(self) -> None:
        """Closes the cache."""
        self._cache.close()
