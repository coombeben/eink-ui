"""
All functions for drawing text to the screen
"""
from PIL import ImageDraw, ImageFont


def truncate_text(draw: type[ImageDraw], text: str, font: type[ImageFont], max_width: int) -> str:
    """Truncates text so that it fits within a given width."""
    # If the text already fits, return it
    text_length = draw.textlength(text=text, font=font)
    if text_length <= max_width:
        return text

    # Else, take a rough estimate of how many characters to keep and truncate
    characters_to_keep = int(len(text) * (max_width / text_length)) - 4
    truncated_text = text[:characters_to_keep]
    while draw.textlength(f'{truncated_text}...', font=font) > max_width:
        truncated_text = truncated_text[:-1]

    return f'{truncated_text}...'


def draw_text_truncated(
        draw: ImageDraw.ImageDraw,
        xy: tuple[float, float],
        text: str,
        font: ImageFont.FreeTypeFont,
        anchor: str,
        max_width: int,
        **kwargs
) -> None:
    """Draws text on `img`, automatically truncating as required."""
    draw.text(xy, truncate_text(draw, text, font, max_width), font=font, anchor=anchor, **kwargs)
