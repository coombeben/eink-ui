"""
Icons
"""
from enum import Enum
from functools import lru_cache

from PIL import Image


class Icon(Enum):
    HEART = 'icons/mdi--heart.png'
    PREVIOUS = 'icons/ic--round-skip-previous.png'
    PAUSE = 'icons/ic--round-pause.png'
    NEXT = 'icons/ic--round-skip-next.png'


@lru_cache(maxsize=None)
def get_icon(icon: Icon) -> Image.Image:
    return Image.open(icon.value)
