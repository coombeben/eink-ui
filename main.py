import logging
import threading
import signal
import warnings
from argparse import ArgumentParser, Namespace
from queue import Queue

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from inky.inky_e673 import Inky
from dotenv import load_dotenv

from buttons import ButtonWorker
from graphics import Canvas, ImageWorker
from renderer import DisplayWorker
from spotify import SpotifyWorker
from models import EvictingQueue, Command, ImageTask, RenderTask

LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s %(levelname)s %(message)s'
DISPLAY_RESOLUTION = (800, 480)
DISPLAY_SATURATION = 0.75
UI_MARGIN = 15
MAX_POLL_TIME = 30  # Maximum time between polls
REQUIRED_SCOPES = ['user-modify-playback-state', 'user-read-playback-state', 'user-library-modify']

logger = logging.getLogger(__name__)

parser = ArgumentParser()
parser.add_argument('--log', default=LOG_LEVEL, help='Set the logging level')
parser.add_argument('--saturation', default=DISPLAY_SATURATION, type=float, help='Set the saturation of the display')

shutdown_event = threading.Event()


def configure_environment(log_level) -> None:
    """Load environment variables from .env file and configure logging."""
    load_dotenv()
    logging.basicConfig(level=log_level, format=LOG_FORMAT)
    warnings.filterwarnings("ignore", message="Busy Wait")

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)


def handle_shutdown(signum: int, frame: object) -> None:
    """Handle SIGTERM and SIGINT signals."""
    shutdown_event.set()


def main(args: Namespace):
    """Main entry point."""
    configure_environment(args.log)

    # Init the inter-thread communication objects
    command_queue: Queue[Command] = Queue()  # Instructions from the GPIO buttons
    processing_queue: EvictingQueue[ImageTask] = EvictingQueue(maxlen=2)  # Tracks to render a background image for
    rendering_queue: EvictingQueue[RenderTask] = EvictingQueue(maxlen=1)  # Images to display on the screen

    # Init the required components
    display = Inky(resolution=DISPLAY_RESOLUTION)
    canvas = Canvas(DISPLAY_RESOLUTION, margin=UI_MARGIN)
    auth_manager = SpotifyOAuth(
        scope=','.join(REQUIRED_SCOPES),
        open_browser=False
    )
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    # Create and start the threads
    spotify_orchestrator = SpotifyWorker(
        spotify,
        command_queue,
        processing_queue,
        shutdown_event,
        poll_interval=MAX_POLL_TIME
    )
    image_processor = ImageWorker(
        canvas,
        processing_queue,
        rendering_queue,
        shutdown_event
    )
    display_renderer = DisplayWorker(
        display,
        rendering_queue,
        shutdown_event,
        display_saturation=args.saturation
    )
    button_handler = ButtonWorker(command_queue, shutdown_event)

    threads = [
        threading.Thread(name='spotify', target=spotify_orchestrator.run),
        threading.Thread(name='processor', target=image_processor.run),
        threading.Thread(name='renderer', target=display_renderer.run),
        threading.Thread(name='buttons', target=button_handler.run)
    ]

    logger.info('Starting threads...')
    for thread in threads:
        thread.start()

    # Run until shutdown
    try:
        shutdown_event.wait()
        logger.info('Received SIGTERM or SIGINT, shutting down.')
    finally:
        for thread in threads:
            thread.join()


if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
