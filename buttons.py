"""
Handles button presses in a background thread
"""
import logging
import threading
from datetime import timedelta
from queue import Queue

import gpiod
import gpiodevice
from gpiod.line import Bias, Direction, Edge
from spotipy import Spotify

from models import Command

# GPIO setup
SW_A = 5
SW_B = 6
SW_C = 16
SW_D = 24
BUTTONS = [SW_A, SW_B, SW_C, SW_D]
LABELS = ["NEXT", "PAUSE", "PREVIOUS", "SAVE"]
INPUT = gpiod.LineSettings(
    direction=Direction.INPUT,
    bias=Bias.PULL_UP,
    edge_detection=Edge.FALLING,
    debounce_period=timedelta(milliseconds=100),
)


class ButtonHandler:
    def __init__(self, spotify: Spotify, command_queue: Queue[Command], shutdown_event: threading.Event):
        self.spotify = spotify
        self.command_queue = command_queue
        self.shutdown_event = shutdown_event

        line_settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP, edge_detection=Edge.FALLING)
        chip = gpiodevice.find_chip_by_platform()
        self.offsets = [chip.line_offset_from_id(button_id) for button_id in BUTTONS]
        line_config = dict.fromkeys(self.offsets, line_settings)
        self.request = chip.request_lines(consumer="spectra6-buttons", config=line_config)

    def _handle_button(self, event: gpiod.EdgeEvent) -> None:
        """Handle a button press."""
        # Identify which button was pressed
        try:
            index = self.offsets.index(event.line_offset)
        except ValueError:
            logging.warning(f'Unidentified button press: {event.line_offset}')
            return
        label = LABELS[index]
        command = Command(label)
        self.command_queue.put(command)

    def _cleanup(self):
        """Clean up on shutdown"""
        logging.info("Stopping button handler...")
        self.request.release()

    def run(self) -> None:
        logging.info("Started button handler")
        while not self.shutdown_event.is_set():
            if self.request.wait_edge_events(timeout=1):
                for event in self.request.read_edge_events():
                    self._handle_button(event)

        self._cleanup()
