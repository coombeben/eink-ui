"""
Thread for rendering images to the display
"""
import threading
import logging

from inky.inky_e673 import Inky

from models import EvictingQueue, RenderTask

__all__ = ['DisplayWorker']

logger = logging.getLogger(__name__)


class DisplayWorker:
    def __init__(
            self,
            display: Inky,
            rendering_queue: EvictingQueue[RenderTask],
            shutdown_event: threading.Event,
            display_saturation: float = 0.5
    ):
        self.display = display
        self.rendering_queue = rendering_queue
        self.shutdown_event = shutdown_event
        self.display_saturation = display_saturation

        self.current_track_id: str | None = None

    def _tick(self, task: RenderTask) -> None:
        """Handles rendering of the given task"""
        logger.debug(f'Received task to render {task.track_id}')

        # Only update the display if the track has changed
        if task.track_id != self.current_track_id:
            logger.debug(f'Rendering {task.track_id}')
            self.current_track_id = task.track_id
            self.display.set_image(task.image, self.display_saturation)
            self.display.show()

    def run(self) -> None:
        """Starts the display rendering thread"""
        logger.info("Started display renderer")
        while not self.shutdown_event.is_set():
            try:
                task = self.rendering_queue.get(timeout=1)
            except TimeoutError:
                continue

            self._tick(task)

        logger.info('Display renderer stopped')
