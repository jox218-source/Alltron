"""Service-owned alarm delivery. A completed deadline is not a played alarm."""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable

from .timers import TimerStore
from .voice import AUDIO_OUTPUT_LOCK, RATE


def play_tone(output_device: str) -> None:
    """Play a short generated tone through the selected service audio device."""
    if not output_device or not shutil.which("aplay"):
        raise RuntimeError("Alarm audio output is unavailable")
    with tempfile.TemporaryDirectory(prefix="alltron-alarm-") as directory:
        path = Path(directory) / "alarm.wav"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as raw:
            with wave.open(raw, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                frames = bytearray()
                for index in range(RATE * 2):
                    phase = index % (RATE // 2)
                    amplitude = 0.18 if phase < RATE // 3 else 0
                    sample = int(32767 * amplitude * math.sin(2 * math.pi * 740 * index / RATE))
                    frames.extend(struct.pack("<h", sample))
                wav.writeframes(frames)
        with AUDIO_OUTPUT_LOCK:
            subprocess.run(["aplay", "-q", "-D", output_device, str(path)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, check=True)


class AlarmService:
    def __init__(self, store: TimerStore, output_device: str = "", *,
                 play: Callable[[], None] | None = None):
        self.store = store
        self.output_device = output_device
        self.play = play or (lambda: play_tone(output_device))
        self.enabled = bool(play) or (bool(output_device) and bool(shutil.which("aplay")))
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.failed = False

    def start(self) -> None:
        if not self.enabled:
            return
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self.stop.is_set():
            self.scan_once()
            self.stop.wait(1)

    def scan_once(self, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        for alarm in self.store.due_alarms(now=timestamp):
            if alarm["due_at"] < timestamp - 300:
                self.store.finish_alarm(alarm["id"], "missed")
                continue
            try:
                self.play()
            except (OSError, RuntimeError, subprocess.SubprocessError):
                self.failed = True
                return
            self.failed = False
            self.store.finish_alarm(alarm["id"], "played")

    def health(self) -> dict:
        if not self.enabled:
            return {"status": "disabled", "verified": False}
        if not self.thread or not self.thread.is_alive() or self.failed:
            return {"status": "unavailable", "verified": False}
        return {"status": "ready", "verified": False}

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
