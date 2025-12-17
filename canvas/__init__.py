"""
Code responsible for generating the PIL image for the display
"""
import functools
from io import BytesIO

import requests
from PIL import Image, ImageDraw
from PIL.Image import Resampling

from .fonts import FontFace, FontSize, get_font
from .image_ops import ThemeColours, generate_vertical_gradient
from .text_ops import truncate_text, draw_text_truncated

__all__ = ['Canvas']


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
theme_colours = ThemeColours()


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
        theme_colour = theme_colours.get(album_art)
        image = generate_vertical_gradient(
            theme_colour,
            self.shape
        )
        draw = ImageDraw.Draw(image)

        # Add the "Playing from" text
        playing_from_text = f'PLAYING FROM {playing_from.upper()}:'
        if not playing_from_title:
            playing_from_text = playing_from_text[:-1]
        draw.text(
            (x_centre, 32),
            playing_from_text,
            fill='white',
            font=get_font(FontFace.SEMIBOLD, FontSize.XS),
            anchor='mt'
        )
        draw_text_truncated(
            draw,
            (x_centre, 50),
            playing_from_title,
            fill='white',
            font=get_font(FontFace.SEMIBOLD, FontSize.SM),
            anchor='mt',
            max_width=max_text_width
        )

        # Add the album art
        album_art = album_art.resize((max_text_width, max_text_width), Resampling.LANCZOS)
        image.paste(album_art, (self.margin, 104))

        # Add the song title, artist, and album title
        draw_text_truncated(
            draw,
            (x_centre, 600),
            song_title,
            fill='white',
            font=get_font(FontFace.BOLD, FontSize.XL),
            anchor='mt',
            max_width=max_text_width
        )
        draw_text_truncated(
            draw,
            (x_centre, 636),
            ', '.join(artists),
            fill='white',
            font=get_font(FontFace.REGULAR, FontSize.BASE),
            anchor='mt',
            max_width=max_text_width
        )
        draw_text_truncated(
            draw,
            (x_centre, 680),
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
