"""Bounded asynchronous frame processor used during live scanning."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QThread, Signal

from .reconstruction import FrameReconstructor


@dataclass(slots=True)
class FramePacket:
    frame_bgr: NDArray[np.uint8]
    timestamp_s: float
    frame_index: int


class ProcessingWorker(QThread):
    processed = Signal(object, object)
    processing_error = Signal(str)

    def __init__(
        self,
        reconstructor: FrameReconstructor,
        background_bgr: NDArray[np.uint8] | None,
    ) -> None:
        super().__init__()
        self.reconstructor = reconstructor
        self.background = None if background_bgr is None else background_bgr.copy()
        self._queue: queue.Queue[FramePacket] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self.dropped_frames = 0

    def submit(self, packet: FramePacket) -> None:
        try:
            self._queue.put_nowait(packet)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self.dropped_frames += 1
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(packet)
            except queue.Full:
                self.dropped_frames += 1

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                packet = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                result = self.reconstructor.process(
                    packet.frame_bgr,
                    frame_index=packet.frame_index,
                    timestamp_s=packet.timestamp_s,
                    background_bgr=self.background,
                )
                self.processed.emit(result, packet.frame_bgr)
            except Exception as error:
                self.processing_error.emit(str(error))
