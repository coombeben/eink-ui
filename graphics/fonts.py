"""
Config for fonts
"""
import functools
from enum import Enum

from PIL import ImageFont

__all__ = ['FontSize', 'FontFace', 'get_font']


class FontSize(Enum):
    XS = 12
    SM = 14
    BASE = 16
    LG = 18
    XL = 20
    XXL = 24


class FontFace(Enum):
    REGULAR = 'fonts/Roboto-Regular.ttf'
    BOLD = 'fonts/Roboto-Bold.ttf'
    SEMIBOLD = 'fonts/Roboto-SemiBold.ttf'
    ITALIC = 'fonts/Roboto-Italic.ttf'


def get_font(face: FontFace, size: FontSize) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(face.value, size.value)
