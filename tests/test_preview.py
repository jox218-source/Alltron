import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from alltron.server import make_server
from alltron.timers import TimerStore


class TimerStoreTests(unittest.TestCase):
    def test_timer_survives_restart_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timers.sqlite3"
            timer = TimerStore(path).add(5, "Tea", now=100.0)
            self.assertEqual(TimerStore(path).list(now=102.0)[0]["state"], "running")
            self.assertEqual(TimerStore(path).list(now=106.0)[0]["state"], "done")
            self.assertEqual(TimerStore(path).list(now=106.0)[0]["id"], timer["id"])

    def test_cancelled_timer_disappears(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TimerStore(Path(directory) / "timers.sqlite3")
            timer = store.add(30, "Laundry")
            self.assertTrue(store.cancel(timer["id"]))
            self.assertFalse(store.cancel(timer["id"]))
            self.assertEqual(store.list(), [])

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions only")
    def test_private_data_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alltron" / "timers.sqlite3"
            TimerStore(path)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions only")
    def test_existing_shared_directory_is_not_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "shared"
            shared.mkdir(mode=0o755)
            os.chmod(shared, 0o755)
            with self.assertRaises(ValueError):
                TimerStore(shared / "timers.sqlite3")
            self.assertEqual(shared.stat().st_mode & 0o777, 0o755)


class PreviewHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = make_server(0, Path(self.directory.name) / "timers.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, path, body=None, origin=None):
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            if origin is not None:
                headers["Origin"] = origin
        request = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_health_and_timer_round_trip(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["local_timers"], "ready")
        status, result = self.request("/api/timers", {"seconds": 60, "label": "Tea"}, self.base)
        self.assertEqual(status, 201)
        status, listing = self.request("/api/timers")
        self.assertEqual(listing["timers"][0]["id"], result["timer"]["id"])

    def test_rejects_foreign_origin_and_invalid_duration(self):
        status, _ = self.request("/api/timers", {"seconds": 60}, "http://example.invalid")
        self.assertEqual(status, 403)
        status, _ = self.request("/api/timers", {"seconds": True}, self.base)
        self.assertEqual(status, 400)

    def test_rejects_forged_host_even_for_reads(self):
        request = Request(self.base + "/api/timers", headers={"Host": "attacker.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
