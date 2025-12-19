"""
Handles button presses in a background thread
"""
import logging
import time
import gpiod
import gpiodevice
from gpiod.line import Bias, Direction, Edge

from spotipy import Spotify

# GPIO setup
SW_A = 5
SW_B = 6
SW_C = 16
SW_D = 24
BUTTONS = [SW_A, SW_B, SW_C, SW_D]
LABELS = ["NEXT", "PAUSE", "PREVIOUS", "SAVE"]
INPUT = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.FALLING)


class ButtonHandler:
    def __init__(self, spotify: Spotify):
        line_settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.FALLING)
        chip = gpiodevice.find_chip_by_platform()
        self.offsets = [chip.line_offset_from_id(button_id) for button_id in BUTTONS]
        line_config = dict.fromkeys(self.offsets, line_settings)
        self.request = chip.request_lines(consumer="spectra6-buttons", config=line_config)
        self.spotify = spotify

    def main_loop(self) -> None:
        while True:
            for event in self.request.read_edge_events():
                self._handle_button(event)
                # Debounce
                time.sleep(0.2)

    def _handle_button(self, event: gpiod.EdgeEvent) -> None:
        """Handle a button press."""
        # Identify which button was pressed
        try:
            index = self.offsets.index(event.line_offset)
        except ValueError:
            logging.warning(f'Unidentified button press: {event.line_offset}')
            return
        label = LABELS[index]

        # Handle button press
        if label == "NEXT":
            self.spotify.next_track()

        elif label == "PAUSE":
            now_playing = self.spotify.currently_playing()
            if not now_playing:
                return
            if now_playing['is_playing'] is True:
                self.spotify.pause_playback()
            else:
                self.spotify.start_playback()
                self.spotify.current_playback()

        elif label == "PREVIOUS":
            self.spotify.previous_track()

        elif label == "SAVE":
            now_playing = self.spotify.currently_playing()
            if not now_playing or now_playing['is_playing'] is False:
                return

            track_id = now_playing['item']['id']
            self.spotify.current_user_saved_tracks_add([track_id])
