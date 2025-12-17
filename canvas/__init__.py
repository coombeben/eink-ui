"""
Code responsible for generating the PIL image for the display
"""
import functools
from io import BytesIO

import requests
from PIL import Image, ImageDraw
from PIL.Image import Resampling

from .fonts import FontFace, FontSize, get_font
from .icons import Icon, get_icon
from .image_ops import get_vibrant_colour, luminance_transform, generate_vertical_gradient
from .text_ops import truncate_text, draw_text_truncated

__all__ = ['Canvas']

BUTTON_SPACING = 120


@functools.lru_cache(maxsize=512)
def fetch_image_bytes(url: str) -> bytes:
    """Fetches image bytes from a URL. Caches results to avoid repeated requests."""
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def get_image_from_url(url: str) -> Image.Image:
    """Loads an image from a URL as a PIL Image."""
    image_bytes = fetch_image_bytes(url)
    with BytesIO(image_bytes) as stream:
        image = Image.open(stream)
        image.load()
    return image


# Class which caches expensive theme colour calculations
# theme_colours = ThemeColours()


class Canvas:
    def __init__(self, shape: tuple[int, int], margin: int = 10):
        """Class responsible for generating the UI"""
        self.shape = shape
        self.rotate_image = False

        if shape[0] > shape[1]:
            self.shape = (shape[1], shape[0])
            self.rotate_image = True

        self.margin = margin

    @property
    def width(self) -> int:
        return self.shape[0]

    @property
    def height(self) -> int:
        return self.shape[1]

    def generate_image(
            self,
            playing_from: str,
            playing_from_title: str,
            album_image_url: str,
            song_title: str,
            artists: list[str],
            album_title: str,
    ) -> Image.Image:
        """Generates the UI given the now playing details."""
        max_text_width = self.width - (2 * self.margin)
        x_centre = self.width // 2

        # Create the background to draw elements on
        album_art = get_image_from_url(album_image_url)
        # theme_colour = theme_colours.get(album_art)
        theme_colour = luminance_transform(get_vibrant_colour(album_art), threshold=3.)
        image = generate_vertical_gradient(
            theme_colour,
            self.shape
        )
        draw = ImageDraw.Draw(image)

        # Add the button icons
        heart_icon = get_icon(Icon.HEART)
        heart_icon_x_pos = self.width // 2 - 3 * BUTTON_SPACING // 2 - heart_icon.size[0] // 2
        image.paste(heart_icon, (heart_icon_x_pos, 0), mask=heart_icon)

        prev_icon = get_icon(Icon.PREVIOUS)
        prev_icon_x_pos = self.width // 2 - BUTTON_SPACING // 2 - prev_icon.size[0] // 2
        image.paste(prev_icon, (prev_icon_x_pos, 0), mask=prev_icon)

        pause_icon = get_icon(Icon.PAUSE)
        pause_icon_x_pos = self.width // 2 + BUTTON_SPACING // 2 - pause_icon.size[0] // 2
        image.paste(pause_icon, (pause_icon_x_pos, 0), mask=pause_icon)

        next_icon = get_icon(Icon.NEXT)
        next_icon_x_pos = self.width // 2 + 3 * BUTTON_SPACING // 2 - next_icon.size[0] // 2
        image.paste(next_icon, (next_icon_x_pos, 0), mask=next_icon)

        # Add the "Playing from" text
        playing_from_text = f'PLAYING FROM {playing_from.upper()}:'
        if not playing_from_title:
            playing_from_text = playing_from_text[:-1]
        draw.text(
            (x_centre, 52),
            playing_from_text,
            fill='white',
            font=get_font(FontFace.SEMIBOLD, FontSize.XS),
            anchor='mt'
        )
        draw_text_truncated(
            draw,
            (x_centre, 70),
            playing_from_title,
            fill='white',
            font=get_font(FontFace.SEMIBOLD, FontSize.SM),
            anchor='mt',
            max_width=max_text_width
        )

        # Add the album art
        album_art = album_art.resize((max_text_width, max_text_width), Resampling.LANCZOS)
        image.paste(album_art, (self.margin, 114))

        # Add the song title, artist, and album title
        draw_text_truncated(
            draw,
            (x_centre, 610),
            song_title,
            fill='white',
            font=get_font(FontFace.BOLD, FontSize.XL),
            anchor='mt',
            max_width=max_text_width
        )
        draw_text_truncated(
            draw,
            (x_centre, 646),
            ', '.join(artists),
            fill='white',
            font=get_font(FontFace.REGULAR, FontSize.BASE),
            anchor='mt',
            max_width=max_text_width
        )
        draw_text_truncated(
            draw,
            (x_centre, 690),
            album_title,
            fill='white',
            font=get_font(FontFace.ITALIC, FontSize.SM),
            anchor='mt',
            max_width=max_text_width
        )

        # We always render in portrait mode, but the display might expect landscape
        if self.rotate_image:
            image = image.transpose(Image.Transpose.ROTATE_90)
        return image
