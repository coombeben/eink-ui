import time
import logging
import warnings
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from inky.inky_e673 import Inky
from dotenv import load_dotenv

from canvas import Canvas

LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s %(levelname)s %(message)s'
DISPLAY_RESOLUTION = (800, 480)
DISPLAY_SATURATION = 0.75
MIN_POLL_TIME = 5  # Minimum time between polls
MAX_POLL_TIME = 30  # Maximum time between polls


def configure_environment() -> None:
    """Load environment variables from .env file and configure logging."""
    load_dotenv()
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
    warnings.filterwarnings("ignore", message="Busy Wait")


def resolve_playback_context(now_playing: dict, spotify: spotipy.Spotify) -> tuple[str, str]:
    """Determine the context from which the current track is playing.
    This is one of playlist/artist/album and the title."""
    context = now_playing['context']
    playing_from = context['type'] if context else 'unknown'
    if playing_from == 'playlist' and context['uri'].endswith('recommended'):
        playing_from = 'recommended'
        playing_from_title = ''
    elif playing_from == 'playlist':
        playlist_info = spotify.playlist(context['uri'], fields='name')
        playing_from_title = playlist_info['name']
    elif playing_from == 'artist':
        playing_from_title = now_playing['item']['artists'][0]['name']
    elif playing_from == 'album':
        playing_from_title = now_playing['item']['album']['name']
    else:
        playing_from_title = ''

    return playing_from, playing_from_title


def main():
    configure_environment()

    display = Inky(resolution=DISPLAY_RESOLUTION)
    canvas = Canvas(DISPLAY_RESOLUTION)
    auth_manager = SpotifyOAuth(
        scope="user-read-playback-state",
        open_browser=False
    )
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    now_playing_track_id = None
    while True:
        # Get the current playback state
        now_playing = spotify.currently_playing()
        if now_playing is None or not now_playing['is_playing']:
            time.sleep(MAX_POLL_TIME)
            continue

        # Calculate when to poll next
        progress_ms = now_playing['progress_ms']
        duration_ms = now_playing['item']['duration_ms']
        next_poll_timestamp = datetime.now() + timedelta(seconds=1, milliseconds=duration_ms - progress_ms)

        # Get context information
        playing_from, playing_from_title = resolve_playback_context(now_playing, spotify)

        # Update display
        if now_playing_track_id != now_playing['item']['id']:
            image = canvas.generate_image(
                playing_from=playing_from,
                playing_from_title=playing_from_title,
                album_image_url=now_playing['item']['album']['images'][0]['url'],
                song_title=now_playing['item']['name'],
                artists=[artist['name'] for artist in now_playing['item']['artists']],
                album_title=now_playing['item']['album']['name']
            )
            display.set_image(image, DISPLAY_SATURATION)
            display.show()
            now_playing_track_id = now_playing['item']['id']

        # Sleep until next poll
        time_until_next_poll = (next_poll_timestamp - datetime.now()).total_seconds()
        next_poll_time = max(min(time_until_next_poll, MAX_POLL_TIME), MIN_POLL_TIME)
        time.sleep(next_poll_time)


if __name__ == '__main__':
    main()
