"""
Code responsible for generating the PIL image for the display
"""
import functools
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO

import requests
from PIL import Image, ImageDraw
from PIL.Image import Resampling

from models import SpotifyTrack, SpotifyContext, EvictingQueue, ImageTask, RenderTask, TrackState
from .fonts import FontFace, FontSize, get_font
from .icons import Icon, get_icon
from .image_ops import ThemeColours, generate_vertical_gradient
from .text_ops import truncate_text, draw_text_truncated

__all__ = ['Canvas', 'ImageProcessor']

BUTTON_SPACING = 120


# Which fonts to use for each element
fonts = {
    "playing_from": get_font(FontFace.SEMIBOLD, FontSize.SM),
    "playing_from_title": get_font(FontFace.SEMIBOLD, FontSize.BASE),
    "title": get_font(FontFace.BOLD, FontSize.XXL),
    "artist": get_font(FontFace.REGULAR, FontSize.LG),
    "album": get_font(FontFace.ITALIC, FontSize.SM),
}


# The layout of the elements on the screen
@dataclass(frozen=True)
class Layout:
    x_centre: int
    margin: int
    max_text_width: int
    controls_y: int = 0
    playing_from_y: int = 72
    playing_from_title_y: int = 96
    album_art_y: int = 0  # Computed
    album_art_shape: tuple[int, int] = (0, 0)  # Computed
    title_y: int = 650
    artist_y: int = 686
    album_y: int = 730


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

        # We always render in portrait mode, but the display might expect landscape
        if shape[0] > shape[1]:
            self.shape = (shape[1], shape[0])
            self.rotate_image = True

        self.layout = self._get_layout(margin)

    @property
    def width(self) -> int:
        return self.shape[0]

    @property
    def height(self) -> int:
        return self.shape[1]

    def _get_layout(self, margin: int) -> Layout:
        """Calculates the layout of the elements on the screen."""
        # In theory, all y pos should be computed, but I only have the one display to test on
        max_text_width = self.width - 2 * margin
        album_art_size = max_text_width
        album_art_shape = (album_art_size, album_art_size)
        album_art_y = (self.height - album_art_size) // 2

        return Layout(
            x_centre=self.width // 2,
            margin=margin,
            max_text_width=max_text_width,
            album_art_y=album_art_y,
            album_art_shape=album_art_shape
        )

    def _create_background(self, album_art: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """Creates a background image with a vertical gradient based off the album art."""
        theme_colour = theme_colours.get(album_art)
        image = generate_vertical_gradient(
            theme_colour,
            self.shape
        )
        draw = ImageDraw.Draw(image)
        return image, draw

    def _draw_controls(self, image: Image.Image) -> None:
        """Draws the favourite/pause/previous/next icons."""
        heart_icon = get_icon(Icon.HEART)
        heart_icon_x_pos = self.layout.x_centre - 3 * BUTTON_SPACING // 2 - heart_icon.size[0] // 2
        image.paste(heart_icon, (heart_icon_x_pos, self.layout.controls_y), mask=heart_icon)

        prev_icon = get_icon(Icon.PREVIOUS)
        prev_icon_x_pos = self.width // 2 - BUTTON_SPACING // 2 - prev_icon.size[0] // 2
        image.paste(prev_icon, (prev_icon_x_pos, self.layout.controls_y), mask=prev_icon)

        pause_icon = get_icon(Icon.PAUSE)
        pause_icon_x_pos = self.width // 2 + BUTTON_SPACING // 2 - pause_icon.size[0] // 2
        image.paste(pause_icon, (pause_icon_x_pos, self.layout.controls_y), mask=pause_icon)

        next_icon = get_icon(Icon.NEXT)
        next_icon_x_pos = self.width // 2 + 3 * BUTTON_SPACING // 2 - next_icon.size[0] // 2
        image.paste(next_icon, (next_icon_x_pos, self.layout.controls_y), mask=next_icon)

    def _draw_playing_from(self, draw: ImageDraw.ImageDraw, playing_from: str, playing_from_title: str) -> None:
        """Draws the playing from text and title."""
        if playing_from_title:
            playing_from_text = f'PLAYING FROM {playing_from.upper()}:'
        else:
            playing_from_text = f'PLAYING FROM { playing_from.upper()}'  # No colon

        draw.text(
            (self.layout.x_centre, self.layout.playing_from_y),
            playing_from_text,
            fill='white',
            font=fonts['playing_from'],
            anchor='mt'
        )
        draw_text_truncated(
            draw,
            (self.layout.x_centre, self.layout.playing_from_title_y),
            playing_from_title,
            fill='white',
            font=fonts['playing_from_title'],
            anchor='mt',
            max_width=self.layout.max_text_width
        )

    def _draw_album_art(self, image: Image.Image, album_art: Image.Image):
        """Draws the album art"""
        album_art = album_art.resize(self.layout.album_art_shape, Resampling.LANCZOS)
        image.paste(album_art, (self.layout.margin, self.layout.album_art_y))

    def _draw_track_info(self, draw: ImageDraw.ImageDraw, song_title: str, artists: list[str], album_title: str) -> None:
        """Draws the song title, artist, and album title"""
        draw_text_truncated(
            draw,
            (self.layout.x_centre, self.layout.title_y),
            song_title,
            fill='white',
            font=fonts['title'],
            anchor='mt',
            max_width=self.layout.max_text_width
        )
        draw_text_truncated(
            draw,
            (self.layout.x_centre, self.layout.artist_y),
            ', '.join(artists),
            fill='white',
            font=fonts['artist'],
            anchor='mt',
            max_width=self.layout.max_text_width
        )
        draw_text_truncated(
            draw,
            (self.layout.x_centre, self.layout.album_y),
            album_title,
            fill='white',
            font=fonts['album'],
            anchor='mt',
            max_width=self.layout.max_text_width
        )

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
        # Create the background to draw elements on
        album_art = get_image_from_url(album_image_url)
        image, draw = self._create_background(album_art)

        # Draw the elements
        self._draw_controls(image)
        self._draw_playing_from(draw, playing_from, playing_from_title)
        self._draw_album_art(image, album_art)
        self._draw_track_info(draw, song_title, artists, album_title)

        # We always render in portrait mode, but the display might expect landscape
        if self.rotate_image:
            image = image.transpose(Image.Transpose.ROTATE_90)

        return image


class ImageProcessor:
    def __init__(
            self,
            processing_queue: EvictingQueue,
            rendering_queue: EvictingQueue,
            canvas: Canvas,
            stop_event: threading.Event
    ):
        self.processing_queue = processing_queue
        self.rendering_queue = rendering_queue
        self.canvas = canvas
        self.stop_event = stop_event

        self.images: OrderedDict[str, Image.Image] = OrderedDict()

    @staticmethod
    def _get_cache_key(track: SpotifyTrack, context: SpotifyContext) -> str:
        return f'{track.id},{context.uri}'

    def _ensure_image(self, track: SpotifyTrack, context: SpotifyContext) -> None:
        """Ensure that an image exists for the given track ID."""
        # Generate the image if it doesn't exist
        cache_id = self._get_cache_key(track, context)
        if cache_id not in self.images:
            self.images[cache_id] = self.canvas.generate_image(
                playing_from=context.type,
                playing_from_title=context.title,
                album_image_url=track.album_image_url,
                song_title=track.song_title,
                artists=track.artists,
                album_title=track.album_title
            )

            # Make sure we only ever store 2 images: the current track and the next track
            self.images.move_to_end(cache_id)
            if len(self.images) > 2:
                self.images.popitem(last=False)

    def run(self):
        """Wait for tasks to arrive in the processing queue and render them to the rendering queue."""
        while not self.stop_event.is_set():
            try:
                task: ImageTask = self.processing_queue.get(timeout=1)
            except TimeoutError:
                continue

            self._ensure_image(task.track, task.context)

            # Only render the image if it's the current track
            if task.state == TrackState.NOW_PLAYING:
                cache_id = self._get_cache_key(task.track, task.context)
                image = self.images.pop(cache_id)
                render_task = RenderTask(track_id=task.track.id, image=image)
                logging.debug(f"ImageProcessor: Request rendering of {task.track.id}")
                self.rendering_queue.put(render_task)
