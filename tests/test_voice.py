"""Local voice orchestration tests use invented PCM and fake engines only."""

import struct
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from alltron.alarms import AlarmService
from alltron.commands import CommandRouter
from alltron.server import handler_for
from http.server import ThreadingHTTPServer
from alltron.timers import TimerStore
from alltron.voice import RATE, VoiceCancelled, VoiceController, VoiceUnavailable, _write_wav


class FakeMicrophone:
    def __init__(self, pcm: bytes):
        self.pcm = pcm
        self.active = False

    def health(self):
        return {"status": "ready"}

    def begin(self):
        self.active = True

    def end(self):
        self.active = False
        return self.pcm

    def cancel(self):
        self.active = False

    def close(self):
        self.active = False


class FakeSpeechEngine:
    def __init__(self):
        self.spoken = []

    def health(self):
        return {"stt": {"status": "ready", "verified": True},
                "tts": {"status": "ready", "verified": True}}

    def transcribe(self, pcm, cancel):
        if cancel.is_set():
            raise VoiceUnavailable("cancelled")
        return "add Oats to shopping list"

    def speak(self, text, cancel):
        self.spoken.append(text)


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = TimerStore(Path(self.directory.name) / "state.sqlite3")

    def tearDown(self):
        self.directory.cleanup()

    def test_silent_and_long_pcm_are_rejected(self):
        path = Path(self.directory.name) / "voice.wav"
        with self.assertRaises(VoiceUnavailable):
            _write_wav(path, b"\x00\x00" * RATE)
        with self.assertRaises(VoiceUnavailable):
            _write_wav(path, struct.pack("<h", 5000) * (RATE * 31))

    def test_local_voice_routes_without_browser_audio(self):
        pcm = struct.pack("<h", 5000) * RATE
        microphone = FakeMicrophone(pcm)
        engine = FakeSpeechEngine()
        voice = VoiceController(microphone, engine, CommandRouter(self.store))
        request_id = voice.begin()
        self.assertTrue(microphone.active)
        voice.end(request_id)
        voice.worker.join(timeout=2)
        types = [event["type"] for event in voice.poll()]
        self.assertEqual(types, ["listening", "transcribing", "transcript", "answer", "speaking", "done"])
        self.assertEqual(self.store.list_shopping_items()[0]["text"], "Oats")
        self.assertIn("Oats", engine.spoken[0])
        self.assertNotIn(pcm, [event.get("audio") for event in voice.poll()])
        voice.close()

    def test_cancelling_capture_releases_microphone(self):
        microphone = FakeMicrophone(b"")
        voice = VoiceController(microphone, FakeSpeechEngine(), CommandRouter(self.store))
        request_id = voice.begin()
        voice.cancel(request_id)
        self.assertFalse(microphone.active)
        self.assertIsNone(voice.current_id)
        self.assertIn("cancelled", [event["type"] for event in voice.poll()])
        voice.close()

    def test_cancel_during_transcription_never_routes_action(self):
        started = threading.Event()
        release = threading.Event()

        class SlowEngine(FakeSpeechEngine):
            def transcribe(self, pcm, cancel):
                started.set()
                release.wait(timeout=2)
                if cancel.is_set():
                    raise VoiceCancelled("cancelled")
                return super().transcribe(pcm, cancel)

        voice = VoiceController(FakeMicrophone(b"sample"), SlowEngine(), CommandRouter(self.store))
        request_id = voice.begin()
        voice.end(request_id)
        self.assertTrue(started.wait(timeout=2))
        voice.cancel(request_id)
        release.set()
        voice.worker.join(timeout=2)
        events = [event for event in voice.poll() if event["request_id"] == request_id]
        self.assertEqual([event["type"] for event in events].count("done"), 1)
        self.assertIn("cancelled", [event["type"] for event in events])
        self.assertEqual(self.store.list_shopping_items(), [])
        voice.close()

    def test_http_push_to_talk_contract_with_fake_audio(self):
        engine = FakeSpeechEngine()
        voice = VoiceController(FakeMicrophone(b"sample"), engine, CommandRouter(self.store))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store, voice))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(path, body):
            request = Request(base + path, data=json.dumps(body).encode(), headers={
                "Origin": base, "Content-Type": "application/json"})
            with urlopen(request, timeout=2) as response:
                return response.status, json.load(response)

        try:
            status, started = post("/api/voice/start", {})
            self.assertEqual(status, 202)
            request_id = started["request_id"]
            status, _ = post("/api/voice/stop", {"request_id": request_id})
            self.assertEqual(status, 202)
            worker = voice.worker
            if worker:
                worker.join(timeout=2)
            with urlopen(base + "/api/voice/events?after=0", timeout=2) as response:
                events = json.load(response)["events"]
            self.assertTrue(all(event["request_id"] == request_id for event in events))
            self.assertIn("done", [event["type"] for event in events])
            self.assertEqual(self.store.list_shopping_items()[0]["text"], "Oats")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            voice.close()

    def test_alarm_is_played_or_explicitly_missed(self):
        played = []
        service = AlarmService(self.store, play=lambda: played.append(True))
        first = self.store.add_alarm(10, now=0)
        service.scan_once(now=10)
        self.assertEqual(played, [True])
        self.assertEqual(self.store.list_alarms()[0]["delivery"], "played")
        second = self.store.add_alarm(20, now=0)
        service.scan_once(now=400)
        by_id = {item["id"]: item for item in self.store.list_alarms()}
        self.assertEqual(by_id[second["id"]]["delivery"], "missed")
        self.assertEqual(by_id[first["id"]]["delivery"], "played")


if __name__ == "__main__":
    unittest.main()
