"""Synthetic-only owner integration tests; no real account or appliance is used."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from alltron.answers import CodexAnswers, CodexCLIRunner
from alltron.commands import CommandRouter
from alltron.home_assistant import HomeAssistant
from alltron.server import handler_for
from alltron.timers import TimerStore


class FakeHA(BaseHTTPRequestHandler):
    calls = []
    response_code = 200

    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.calls.append((self.path, self.headers.get("Authorization"), json.loads(body)))
        self.send_response(self.response_code)
        if self.response_code == 302:
            self.send_header("Location", "http://example.invalid/collect")
        self.end_headers()
        self.wfile.write(b"[]")


class OwnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.token_file = self.root / "owner-token"
        self.token_file.write_text("invented-test-token\n", encoding="utf-8")
        if os.name == "posix":
            self.token_file.chmod(0o600)
        FakeHA.calls = []
        FakeHA.response_code = 200
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHA)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.ha = HomeAssistant(self.server.server_port, self.token_file,
                                {"Porch Lamp": "light.porch_lamp"})
        self.router = CommandRouter(TimerStore(self.root / "state.sqlite3"), home_assistant=self.ha)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def test_selected_device_only_and_fixed_services(self):
        result = self.router.execute("Turn on the porch lamp")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(FakeHA.calls, [(
            "/api/services/light/turn_on", "Bearer invented-test-token",
            {"entity_id": "light.porch_lamp"})])
        self.assertEqual(self.router.execute("Turn off kitchen oven")["status"], "not-allowed")
        self.assertEqual(len(FakeHA.calls), 1)

    def test_auth_error_and_redirect_are_bounded(self):
        FakeHA.response_code = 401
        self.assertEqual(self.router.execute("turn off porch lamp")["status"], "auth-error")
        FakeHA.response_code = 302
        self.assertEqual(self.router.execute("turn off porch lamp")["status"], "service-error")
        self.assertEqual(len(FakeHA.calls), 2)

    def test_missing_token_fails_closed_without_network_request(self):
        self.token_file.unlink()
        result = self.router.execute("turn on porch lamp")
        self.assertEqual(result["status"], "auth-error")
        self.assertEqual(FakeHA.calls, [])

    def test_owner_config_rejects_broad_and_unsafe_targets(self):
        for entity in ("lock.front_door", "light.*", "light.porch_lamp/../../other"):
            with self.assertRaises(ValueError):
                HomeAssistant(self.server.server_port, self.token_file, {"lamp": entity})
        with self.assertRaises(ValueError):
            HomeAssistant(self.server.server_port, self.token_file, {"Lamp": "light.a", "lamp": "light.b"})
        config = self.root / "ha.json"
        config.write_text(json.dumps({"port": self.server.server_port,
                                      "token_file": str(self.token_file),
                                      "aliases": {"Porch Lamp": "light.porch_lamp"}}), encoding="utf-8")
        if os.name == "posix":
            config.chmod(0o600)
        self.assertEqual(HomeAssistant.from_file(config).health(), "configured")

    def test_questions_cannot_trigger_home_assistant(self):
        asked = []
        router = CommandRouter(self.router.store, home_assistant=self.ha,
                               answers=CodexAnswers(lambda question: asked.append(question) or "A short answer."))
        result = router.execute("What is a light switch?")
        self.assertEqual(result["kind"], "answer")
        self.assertEqual(len(asked), 1)
        self.assertEqual(FakeHA.calls, [])
        self.assertEqual(router.execute("turn on the porch lamp")["kind"], "home-assistant")
        self.assertEqual(len(asked), 1)

    def test_loopback_api_reports_configuration_and_routes_selected_action(self):
        app = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.router.store, router=self.router))
        worker = threading.Thread(target=app.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{app.server_port}"
        try:
            with urlopen(base + "/api/health", timeout=3) as response:
                self.assertEqual(json.load(response)["home_assistant"], "configured")
            request = Request(base + "/api/commands",
                              data=json.dumps({"text": "turn on porch lamp"}).encode(),
                              headers={"Origin": base, "Content-Type": "application/json"})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(json.load(response)["status"], "ok")
            self.assertEqual(len(FakeHA.calls), 1)
        finally:
            app.shutdown()
            app.server_close()
            worker.join(timeout=2)

    def test_codex_failure_modes_do_not_expose_stderr(self):
        self.assertEqual(CodexAnswers(lambda _: "").answer("What time is it?")["status"], "unavailable")
        def timeout(_question):
            raise subprocess.TimeoutExpired("fake", 1)
        self.assertEqual(CodexAnswers(timeout).answer("Why?")["status"], "timeout")
        def failed(_question):
            raise subprocess.CalledProcessError(1, ["fake"], stderr="private diagnostic")
        result = CodexAnswers(failed).answer("Why?")
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("private diagnostic", str(result))

    def test_cli_transport_passes_bounded_prompt_without_shell(self):
        empty = self.root / "empty"
        empty.mkdir()
        codex_home = self.root / "codex-profile"
        codex_home.mkdir()
        process_home = self.root / "runner-home"
        process_home.mkdir()
        fake = self.root / "fake_cli.py"
        fake.write_text("import sys\nassert sys.argv[1:3] == ['exec', '--ephemeral']\n"
                        "assert sys.argv[-1] == '-'\n"
                        "prompt = sys.stdin.read()\nassert 'Question: Why is the sky blue?' in prompt\n"
                        "print('Because of scattering.')\n", encoding="utf-8")
        runner = CodexCLIRunner((sys.executable, str(fake)), empty, codex_home, process_home)
        self.assertNotIn("ALLTRON_HA_CONFIG", runner.environment)
        self.assertNotIn("OPENAI_API_KEY", runner.environment)
        result = CodexAnswers(runner).answer("Why is the sky blue?")
        self.assertEqual(result["text"], "Because of scattering.")


if __name__ == "__main__":
    unittest.main()
