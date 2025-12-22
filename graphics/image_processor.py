"""
The ImageProcessor thread.

Responsible processing requests for images to be generated for the display
"""
import logging
import threading
from collections import OrderedDict

from PIL import Image

from models import SpotifyTrack, SpotifyContext, EvictingQueue, ImageTask, RenderTask, TrackState
from .canvas import Canvas


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
        """Returns a unique key for the given track and context."""
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

    def _close(self) -> None:
        """Cleans up any resources used by the image processor."""
        logging.info('Image processor stopping...')
        self.canvas.close()

    def run(self):
        """Wait for tasks to arrive in the processing queue and render them to the rendering queue."""
        logging.info('Started image processor')
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

        self._close()
