"""
Common data models and classes used throughout the application.
"""
import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Generic, Self, TypeVar, Literal

from PIL import Image

__all__ = ['EvictingQueue', 'Command', 'SpotifyTrack', 'SpotifyContext', 'TrackState', 'ImageTask', 'RenderTask']


_T = TypeVar("_T")


class EvictingQueue(Generic[_T]):
    def __init__(self, maxlen: int):
        """
        A thread-safe FIFO queue with a maximum length.
        Different from `queue.Queue` as new puts push out old values rather than blocking
        """
        self.deque = deque(maxlen=maxlen)
        self.cond = threading.Condition()

    def put(self, item: _T) -> None:
        with self.cond:
            self.deque.append(item)
            self.cond.notify()

    def get(self, timeout: float | None = None) ->_T:
        """Remove and return an item from the queue."""
        with self.cond:
            while not self.deque:
                wait_success = self.cond.wait(timeout=timeout)
                if not wait_success:
                    raise TimeoutError
            return self.deque.popleft()


class Command(Enum):
    NEXT = "NEXT"
    PREVIOUS = "PREVIOUS"
    SAVE = "SAVE"
    PAUSE = "PAUSE"


@dataclass
class SpotifyTrack:
    id: str
    album_image_url: str
    song_title: str
    artists: list[str]
    album_title: str
    duration_ms: int

    @classmethod
    def from_track_object(cls, track: dict) -> Self:
        """Creates a SpotifyTrack from a Spotify API track object."""
        return cls(
            id=track['id'],
            album_image_url=track['album']['images'][0]['url'],
            song_title=track['name'],
            artists=[artist['name'] for artist in track['artists']],
            album_title=track['album']['name'],
            duration_ms=track['duration_ms']
        )


PlayingFrom = Literal['playlist', 'artist', 'album', 'recommended', 'unknown']


@dataclass
class SpotifyContext:
    uri: str
    type: PlayingFrom
    title: str


class TrackState(Enum, int):
    NOW_PLAYING = 0
    NEXT_UP = 1


@dataclass
class ImageTask:
    state: TrackState
    track: SpotifyTrack
    context: SpotifyContext


@dataclass
class RenderTask:
    track_id: str
    image: Image.Image
