"""
The Spotify Orchestrator thread.

The Orchestrator tracks the state of Spotify playback and updates the rendering queue accordingly.
"""
import logging
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty

from spotipy import Spotify

from models import Command, SpotifyTrack, SpotifyContext, TrackState, EvictingQueue, ImageTask

__all__ = ['SpotifyOrchestrator']


@dataclass
class PlaybackState:
    now_playing: SpotifyTrack | None
    next_up: SpotifyTrack | None
    context: SpotifyContext | None
    now_playing_end_time: float = float('inf')


class SpotifyOrchestrator:
    def __init__(self, spotify: Spotify, command_queue: Queue, processing_queue: EvictingQueue, shutdown_event: threading.Event, poll_interval: float = 10):
        """Class to keep track of the Spotify playback state and update the rendering queue accordingly."""
        self.spotify = spotify
        self.command_queue = command_queue
        self.processing_queue = processing_queue
        self.poll_interval = poll_interval
        self._next_fetch_time = time.monotonic() + poll_interval
        self.shutdown_event = shutdown_event

        self.state: PlaybackState | None = None
        self.state = self.get_playback_state()

    def _get_playback_context(self, currently_playing: dict) -> SpotifyContext | None:
        """Determine the context from which the current track is playing.
        This is one of playlist/artist/album and the title."""
        current_contxt = self.state.context if self.state else None
        context = currently_playing.get('context')
        context_uri = context.get('uri')

        # If our context hasn't changed, return the current context
        if self.state and context_uri == self.state.context.uri:
            return current_contxt

        playing_from = context['type'] if context else 'unknown'
        if playing_from == 'playlist' and context_uri.endswith('recommended'):
            playing_from = 'recommended'
            playing_from_title = ''
        elif playing_from == 'playlist':
            playlist_info = self.spotify.playlist(context_uri, fields='name')
            playing_from_title = playlist_info['name']
        elif playing_from == 'artist':
            playing_from_title = currently_playing['item']['artists'][0]['name']
        elif playing_from == 'album':
            playing_from_title = currently_playing['item']['album']['name']
        else:
            playing_from_title = ''

        return SpotifyContext(
            uri=context_uri,
            type=playing_from,
            title=playing_from_title
        )

    def get_playback_state(self) -> PlaybackState | None:
        """Returns the current playback state."""
        # Get the current track and the next track in the queue from the Spotify API
        currently_playing = self.spotify.currently_playing()
        if not currently_playing:
            return None
        play_queue = self.spotify.queue()

        # Create objects for PlaybackState
        # Note that as we cannot get both `currently_playing` and `play_queue` in a single request,
        # they might disagree.
        now_playing = SpotifyTrack.from_track_object(play_queue['currently_playing'])
        now_playing_end_time = time.monotonic() + (now_playing.duration_ms - currently_playing['progress_ms']) / 1000
        next_up = SpotifyTrack.from_track_object(play_queue['queue'][0])
        context = self._get_playback_context(currently_playing)

        return PlaybackState(
            now_playing=now_playing,
            next_up=next_up,
            context=context,
            now_playing_end_time=now_playing_end_time
        )

    def _enqueue_processing_updates(self) -> None:
        """Add the now playing and next-up tracks to the processing queue."""
        now_playing_task = ImageTask(
            state=TrackState.NOW_PLAYING,
            track=self.state.now_playing,
            context=self.state.context
        )
        next_up_task = ImageTask(
            state=TrackState.NEXT_UP,
            track=self.state.next_up,
            context=self.state.context
        )
        logging.debug(f'SpotifyOrchestrator: Enqueued {now_playing_task}')
        logging.debug(f'SpotifyOrchestrator: Enqueued {next_up_task}')
        self.processing_queue.put(now_playing_task)
        self.processing_queue.put(next_up_task)
        
    def handle_command(self, command: Command) -> bool:
        """Executes the given command and returns whether a refresh is required."""
        refresh_required = False
        
        if command == Command.NEXT:
            self.spotify.next_track()
            # Currently playing track changed => refresh
            refresh_required = True

        elif command == Command.PREVIOUS:
            self.spotify.previous_track()
            # Currently playing track changed => refresh
            refresh_required = True

        elif command == Command.SAVE:
            track_id = self.state.now_playing.id
            self.spotify.current_user_saved_tracks_add([track_id])
            # Saving a track does not require a refresh

        elif command == Command.PAUSE:
            now_playing = self.spotify.currently_playing()
            if not now_playing:
                return refresh_required
            if now_playing.get('is_playing'):
                self.spotify.pause_playback()
            else:
                self.spotify.start_playback()
            # Play/pause does not require a refresh
        
        return refresh_required

    def _update_next_fetch_time(self) -> None:
        """Updates the next fetch time."""
        # We either fetch at the end of the current track or after `poll_interval` seconds, whichever is sooner
        track_end_time = float('inf')
        if self.state:
            track_end_time = self.state.now_playing_end_time

        default_poll_time = time.monotonic() + self.poll_interval
        self._next_fetch_time = min(track_end_time, default_poll_time)

    def tick(self, command: Command | None = None) -> None:
        """Handles commands; updates state; enqueues processing"""
        refresh_required = self.handle_command(command) if command else True
        if not refresh_required:
            return

        state = self.get_playback_state()
        if state != self.state:
            self.state = state
            self._enqueue_processing_updates()

        self._update_next_fetch_time()

    def run(self) -> None:
        """Starts the Spotify Orchestrator thread."""
        logging.info('Spotify Orchestrator started.')
        while not self.shutdown_event.is_set():
            command = None
            timeout = max(self._next_fetch_time - time.monotonic(), 0)
            try:
                command = self.command_queue.get(timeout=timeout)
            except Empty:
                pass

            self.tick(command)

        logging.info('Spotify Orchestrator stopped.')
