"""Service-owned, opt-in local speech path for the developer preview.

The browser sends control events only. It never owns the microphone or sends audio.
No audio or transcript is written to the Alltron database or request logs.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandRouter


RATE = 16_000
MAX_SECONDS = 30
CHUNK_BYTES = RATE * 2 // 10
AUDIO_OUTPUT_LOCK = threading.Lock()


class VoiceUnavailable(RuntimeError):
    pass


class VoiceCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceConfig:
    audio_input: str = ""
    audio_output: str = ""
    whisper_bin: str = ""
    whisper_model: str = ""
    piper_python: str = ""
    piper_model: str = ""
    piper_config: str = ""
    scratch_dir: str = ""
    whisper_threads: int = 2

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        return cls(
            audio_input=os.getenv("ALLTRON_AUDIO_INPUT", ""),
            audio_output=os.getenv("ALLTRON_AUDIO_OUTPUT", ""),
            whisper_bin=os.getenv("ALLTRON_WHISPER_BIN", ""),
            whisper_model=os.getenv("ALLTRON_WHISPER_MODEL", ""),
            piper_python=os.getenv("ALLTRON_PIPER_PYTHON", ""),
            piper_model=os.getenv("ALLTRON_PIPER_MODEL", ""),
            piper_config=os.getenv("ALLTRON_PIPER_CONFIG", ""),
            scratch_dir=os.getenv("ALLTRON_VOICE_SCRATCH", ""),
            whisper_threads=int(os.getenv("ALLTRON_WHISPER_THREADS", "2")),
        )


def _executable(path: str) -> bool:
    return bool(path) and Path(path).is_file() and os.access(path, os.X_OK)


def _model(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def _run(args: list[str], *, cancel: threading.Event, timeout: float) -> bytes:
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel.is_set():
                raise VoiceCancelled("Speech request cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VoiceUnavailable("Speech engine timed out")
            try:
                output, _ = process.communicate(timeout=min(0.2, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise VoiceUnavailable("Speech engine failed")
        if len(output) > 16_000:
            raise VoiceUnavailable("Speech engine output was too large")
        return output
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def _write_wav(path: Path, pcm: bytes) -> None:
    if not 0.2 * RATE * 2 <= len(pcm) <= MAX_SECONDS * RATE * 2 or len(pcm) % 2:
        raise VoiceUnavailable("Recording length is outside the supported range")
    samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
    if rms < 0.003:
        raise VoiceUnavailable("No speech was detected")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as raw:
        with wave.open(raw, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(pcm)


class SpeechEngine:
    def __init__(self, config: VoiceConfig):
        self.config = config
        self.stt_verified = False
        self.tts_verified = False

    def health(self) -> dict:
        stt_configured = bool(self.config.whisper_bin and self.config.whisper_model)
        tts_configured = bool(self.config.piper_python and self.config.piper_model and
                              self.config.piper_config and self.config.audio_output)
        stt_ready = _executable(self.config.whisper_bin) and _model(self.config.whisper_model)
        tts_ready = (_executable(self.config.piper_python) and _model(self.config.piper_model) and
                     _model(self.config.piper_config) and bool(self.config.audio_output) and
                     bool(shutil.which("aplay")))
        return {
            "stt": {"status": "ready" if stt_ready else "unavailable" if stt_configured else "disabled",
                    "verified": self.stt_verified},
            "tts": {"status": "ready" if tts_ready else "unavailable" if tts_configured else "disabled",
                    "verified": self.tts_verified},
        }

    def transcribe(self, pcm: bytes, cancel: threading.Event) -> str:
        if self.health()["stt"]["status"] != "ready":
            raise VoiceUnavailable("Speech recognition is not configured")
        with tempfile.TemporaryDirectory(dir=self.config.scratch_dir or None, prefix="alltron-stt-") as directory:
            path = Path(directory) / "audio.wav"
            _write_wav(path, pcm)
            output = _run([self.config.whisper_bin, "-m", self.config.whisper_model,
                           "-f", str(path), "-t", str(self.config.whisper_threads), "-nt", "-np"],
                          cancel=cancel, timeout=45)
        transcript = output.decode("utf-8", errors="replace").strip()
        if transcript.lower() in {"[blank_audio]", "[silence]", "[no speech]"}:
            return ""
        if transcript:
            self.stt_verified = True
        return transcript[:500]

    def speak(self, text: str, cancel: threading.Event) -> None:
        if self.health()["tts"]["status"] != "ready":
            raise VoiceUnavailable("Speech output is not configured")
        if not text or len(text) > 500:
            raise ValueError("Speech text must contain 1 to 500 characters")
        with tempfile.TemporaryDirectory(dir=self.config.scratch_dir or None, prefix="alltron-tts-") as directory:
            path = Path(directory) / "reply.wav"
            _run([self.config.piper_python, "-m", "piper", "-m", self.config.piper_model,
                  "-c", self.config.piper_config, "-f", str(path), "--", text],
                 cancel=cancel, timeout=45)
            if not path.is_file() or path.stat().st_size < 44:
                raise VoiceUnavailable("Speech output was empty")
            with AUDIO_OUTPUT_LOCK:
                _run(["aplay", "-q", "-D", self.config.audio_output, str(path)],
                     cancel=cancel, timeout=120)
        self.tts_verified = True


class PersistentMicrophone:
    """One ALSA recorder process supplies every request; browser reloads cannot claim it."""

    def __init__(self, device: str):
        self.device = device
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.recording: bytearray | None = None
        self.started_at = 0.0

    def start(self) -> None:
        if not self.device:
            raise VoiceUnavailable("Select a microphone before enabling voice")
        if self.process is not None and self.process.poll() is None:
            return
        if not shutil.which("arecord"):
            raise VoiceUnavailable("Audio recorder is unavailable")
        self.process = subprocess.Popen(
            ["arecord", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(RATE),
             "-c", "1", "-t", "raw", "-"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while self.process.poll() is None:
            chunk = self.process.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            with self.lock:
                if self.recording is not None:
                    self.recording.extend(chunk)
                    if len(self.recording) > RATE * 2 * MAX_SECONDS:
                        self.recording = None

    def health(self) -> dict:
        if not self.device:
            return {"status": "disabled"}
        return {"status": "ready" if self.process is not None and self.process.poll() is None
                else "unavailable"}

    def begin(self) -> None:
        if self.health()["status"] != "ready":
            raise VoiceUnavailable("Microphone is unavailable")
        with self.lock:
            if self.recording is not None:
                raise VoiceUnavailable("A recording is already active")
            self.recording = bytearray()
            self.started_at = time.monotonic()

    def end(self) -> bytes:
        with self.lock:
            if self.recording is None:
                raise VoiceUnavailable("Recording ended or reached the time limit")
            audio = bytes(self.recording)
            self.recording = None
            return audio

    def cancel(self) -> None:
        with self.lock:
            self.recording = None

    def close(self) -> None:
        self.cancel()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.thread is not None:
            self.thread.join(timeout=2)


class VoiceController:
    def __init__(self, microphone: PersistentMicrophone | None, engine: SpeechEngine | None,
                 router: CommandRouter):
        self.microphone, self.engine, self.router = microphone, engine, router
        self.lock = threading.Lock()
        self.current_id: str | None = None
        self.phase = "idle"
        self.cancel_event = threading.Event()
        self.events: deque[dict] = deque(maxlen=100)
        self.sequence = 0
        self.worker: threading.Thread | None = None

    def health(self) -> dict:
        engine = self.engine.health() if self.engine else {
            "stt": {"status": "disabled", "verified": False},
            "tts": {"status": "disabled", "verified": False}}
        return {"wake": {"status": "disabled"},
                "capture": self.microphone.health() if self.microphone else {"status": "disabled"},
                **engine}

    def _event(self, kind: str, *, request_id: str | None = None, **fields) -> None:
        with self.lock:
            self.sequence += 1
            self.events.append({"sequence": self.sequence, "type": kind,
                                "request_id": request_id or self.current_id, "at": time.time(), **fields})

    def begin(self) -> str:
        if self.microphone is None or self.engine is None:
            raise VoiceUnavailable("Voice is not configured")
        if self.engine.health()["stt"]["status"] != "ready":
            raise VoiceUnavailable("Speech recognition is unavailable")
        with self.lock:
            if self.current_id is not None:
                raise VoiceUnavailable("A voice request is already active")
            self.microphone.begin()
            self.current_id = str(uuid.uuid4())
            self.phase = "capturing"
            self.cancel_event = threading.Event()
            request_id = self.current_id
        self._event("listening", request_id=request_id)
        return request_id

    def end(self, request_id: str) -> None:
        with self.lock:
            if request_id != self.current_id or self.phase != "capturing":
                raise VoiceUnavailable("Voice request is no longer active")
            assert self.microphone is not None
            try:
                audio = self.microphone.end()
            except VoiceUnavailable as exc:
                self.current_id = None
                self.phase = "idle"
                error = str(exc)[:160]
            else:
                error = None
                self.phase = "processing"
                self.worker = threading.Thread(target=self._process, args=(audio, request_id), daemon=True)
                self.worker.start()
        if error is not None:
            self._event("error", request_id=request_id, text=error)
            self._event("done", request_id=request_id)
            raise VoiceUnavailable(error)

    def _process(self, pcm: bytes, request_id: str) -> None:
        assert self.engine is not None
        try:
            self._event("transcribing", request_id=request_id)
            transcript = self.engine.transcribe(pcm, self.cancel_event)
            if self.cancel_event.is_set():
                raise VoiceCancelled("Speech request cancelled")
            if not transcript:
                raise VoiceUnavailable("No speech was recognized")
            self._event("transcript", request_id=request_id, text=transcript)
            with self.lock:
                if self.cancel_event.is_set():
                    raise VoiceCancelled("Speech request cancelled")
                answer = self.router.execute(transcript, request_id=request_id)
            self._event("answer", request_id=request_id, command_kind=answer["kind"],
                        status=answer["status"], text=answer["text"])
            if self.engine.health()["tts"]["status"] == "ready":
                self._event("speaking", request_id=request_id)
                self.engine.speak(answer["text"], self.cancel_event)
        except VoiceCancelled:
            self._event("cancelled", request_id=request_id)
        except (VoiceUnavailable, ValueError, OSError) as exc:
            self._event("error", request_id=request_id, text=str(exc)[:160])
        except Exception:
            self._event("error", request_id=request_id, text="Speech request failed")
        finally:
            self._event("done", request_id=request_id)
            with self.lock:
                if self.current_id == request_id:
                    self.current_id = None
                    self.phase = "idle"
                    self.worker = None

    def cancel(self, request_id: str) -> None:
        with self.lock:
            if request_id != self.current_id:
                raise VoiceUnavailable("Voice request is no longer active")
            self.cancel_event.set()
            capturing = self.phase == "capturing"
            if self.microphone:
                self.microphone.cancel()
            if capturing:
                self.current_id = None
                self.phase = "idle"
        if capturing:
            self._event("cancelled", request_id=request_id)
            self._event("done", request_id=request_id)

    def poll(self, after: int = 0) -> list[dict]:
        now = time.time()
        with self.lock:
            while self.events and now - self.events[0]["at"] > 120:
                self.events.popleft()
            return [event.copy() for event in self.events if event["sequence"] > after]

    def close(self) -> None:
        self.cancel_event.set()
        if self.microphone:
            self.microphone.close()
        if self.worker:
            self.worker.join(timeout=2)
