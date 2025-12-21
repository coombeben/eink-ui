"""
Thread for rendering images to the display
"""
import threading
import logging

from inky.inky_e673 import Inky

from models import EvictingQueue, RenderTask

__all__ = ['DisplayRenderer']


class DisplayRenderer:
    def __init__(self, display: Inky, rendering_queue: EvictingQueue[RenderTask], shutdown_event: threading.Event, display_saturation: float = 0.5):
        self.display = display
        self.rendering_queue = rendering_queue
        self.shutdown_event = shutdown_event
        self.display_saturation = display_saturation

        self.current_track_id: str | None = None

    def run(self):
        logging.info("Started display renderer")
        while not self.shutdown_event.is_set():
            try:
                display_image = self.rendering_queue.get(timeout=1)
            except TimeoutError:
                continue
            logging.debug(f"DisplayRenderer: Received task to render {display_image.track_id}")

            # Only update the display if the track has changed
            if display_image.track_id != self.current_track_id:
                logging.debug(f"DisplayRenderer: Rendering {display_image.track_id}")
                self.current_track_id = display_image.track_id
                self.display.set_image(display_image.image, self.display_saturation)
                self.display.show()

        logging.info('Display renderer stopped')