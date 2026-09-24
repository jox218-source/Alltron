"""Public-only local command and persistence acceptance tests."""

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from alltron.commands import CommandRouter
from alltron.server import make_server
from alltron.timers import TimerStore


class LocalCoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "alltron.sqlite3"
        self.store = TimerStore(self.path)
        self.router = CommandRouter(self.store)

    def tearDown(self):
        self.directory.cleanup()

    def test_upgrade_preserves_existing_timer_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("DROP TABLE timers")
                db.execute("CREATE TABLE timers (id TEXT PRIMARY KEY, label TEXT NOT NULL, "
                           "created_at REAL NOT NULL, due_at REAL NOT NULL, state TEXT NOT NULL)")
                db.execute("INSERT INTO timers VALUES ('old', 'Tea', 100, 200, 'running')")
        upgraded = TimerStore(self.path)
        self.assertEqual(upgraded.list(now=150)[0]["id"], "old")
        self.assertEqual(upgraded.add(30, "Rice", now=150, request_id="example")["label"], "Rice")

    def test_command_retry_reuses_timer_and_alarm(self):
        first = self.router.execute("set a timer for 5 minutes named Tea", request_id="one", now=100)
        again = self.router.execute("set a timer for 5 minutes named Tea", request_id="one", now=101)
        self.assertEqual(first["timer"]["id"], again["timer"]["id"])
        self.assertEqual(len(self.store.list(now=100)), 1)
        with self.assertRaises(ValueError):
            self.router.execute("set a timer for 6 minutes named Tea", request_id="one", now=101)
        alarm_router = CommandRouter(self.store, alarm_available=lambda: True)
        alarm = alarm_router.execute("set an alarm in 10 minutes", request_id="two", now=100)
        retry = alarm_router.execute("set an alarm in 10 minutes", request_id="two", now=101)
        self.assertEqual(alarm["alarm"]["id"], retry["alarm"]["id"])
        self.assertEqual(TimerStore(self.path).list_alarms(now=101)[0]["state"], "running")
        self.assertEqual(TimerStore(self.path).list_alarms(now=701)[0]["state"], "running")
        self.assertTrue(self.store.finish_alarm(alarm["alarm"]["id"], "played"))
        self.assertEqual(TimerStore(self.path).list_alarms()[0]["delivery"], "played")

    def test_shopping_list_deduplicates_active_item_and_survives_restart(self):
        added = self.router.execute("add Oats to my shopping list", now=100)
        duplicate = self.router.execute("add oats to the shopping list", now=101)
        self.assertEqual(added["item"]["id"], duplicate["item"]["id"])
        self.assertEqual(len(TimerStore(self.path).list_shopping_items()), 1)
        self.assertTrue(self.store.complete_shopping_item(added["item"]["id"]))
        new = self.store.add_shopping_item("Oats", now=102)
        self.assertNotEqual(new["id"], added["item"]["id"])
        self.assertEqual(len(TimerStore(self.path).list_shopping_items()), 2)

    def test_shopping_command_retries_do_not_repeat_actions(self):
        added = self.router.execute("add Oats to my shopping list", request_id="add-one")
        done = self.router.execute("complete Oats on my shopping list", request_id="done-one")
        self.assertEqual(done["status"], "ok")
        self.assertEqual(self.router.execute("complete Oats on my shopping list",
                                             request_id="done-one")["status"], "ok")
        retry = self.router.execute("add Oats to my shopping list", request_id="add-one")
        self.assertEqual(added["item"]["id"], retry["item"]["id"])
        self.assertEqual(len([item for item in self.store.list_shopping_items() if not item["done"]]), 0)
        with self.assertRaises(ValueError):
            self.router.execute("add Milk to my shopping list", request_id="add-one")

    def test_concurrent_duplicate_timer_request_has_one_result(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.router.execute(
                "set a timer for 5 minutes", request_id="same", now=100), range(4)))
        self.assertEqual(len({result["timer"]["id"] for result in results}), 1)
        self.assertEqual(len(self.store.list(now=100)), 1)

    def test_unknown_and_unconfigured_actions_do_not_mutate(self):
        self.assertEqual(self.router.execute("set an alarm in 10 minutes")["status"], "unavailable")
        self.assertEqual(self.router.execute("Turn on the porch lights")["status"], "not-configured")
        self.assertEqual(self.router.execute("delete everything")["status"], "unavailable")
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.store.list_shopping_items(), [])


class LocalHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = make_server(0, Path(self.directory.name) / "alltron.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, path, body=None, *, origin=None):
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Origin"] = origin or self.base
        request = Request(self.base + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_command_and_list_round_trip(self):
        status, added = self.request("/api/commands", {"text": "add Oats to shopping list",
                                                        "request_id": "87627efe-5312-4301-b5f5-eb043f956d36"})
        self.assertEqual(status, 200)
        self.assertEqual(added["kind"], "shopping")
        status, listing = self.request("/api/lists/shopping")
        self.assertEqual(status, 200)
        self.assertEqual(listing["items"][0]["text"], "Oats")
        status, completed = self.request("/api/lists/shopping/complete", {"id": listing["items"][0]["id"]})
        self.assertEqual((status, completed), (200, {"completed": True}))

    def test_voice_health_is_truthful_and_command_origin_checked(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["voice"]["stt"]["status"], "disabled")
        status, _ = self.request("/api/commands", {"text": "time"}, origin="http://example.invalid")
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
