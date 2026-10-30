import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from starlette.types import Message, Scope

from app.workbench import mount_workbench


async def get(app: FastAPI, path: str) -> tuple[int, bytes, dict[bytes, bytes]]:
    messages: list[Message] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], body, dict(start["headers"])


class WorkbenchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.build_directory = self.directory / "dist"
        (self.build_directory / "assets").mkdir(parents=True)
        (self.build_directory / "index.html").write_text(
            '<h1>Workbench shell</h1><script src="/workbench/assets/app.js"></script>',
            encoding="utf-8",
        )
        (self.build_directory / "assets" / "app.js").write_text(
            'console.log("shell");',
            encoding="utf-8",
        )
        (self.directory / "private.txt").write_text("not public", encoding="utf-8")
        self.app = self.make_app(self.build_directory)

    def make_app(self, build_directory: Path) -> FastAPI:
        app = FastAPI()
        mount_workbench(app, build_directory=build_directory)

        @app.get("/v1/probe")
        def probe() -> dict[str, bool]:
            return {"ok": True}

        return app

    async def test_serves_index_at_workbench_base(self):
        status, body, headers = await get(self.app, "/workbench/")
        self.assertEqual(status, 200)
        self.assertIn(b"Workbench shell", body)
        self.assertIn(b"text/html", headers[b"content-type"])

    async def test_serves_javascript_under_workbench_base(self):
        status, body, headers = await get(self.app, "/workbench/assets/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(body, b'console.log("shell");')
        self.assertIn(b"javascript", headers[b"content-type"])

    async def test_redirects_base_without_trailing_slash(self):
        status, _, headers = await get(self.app, "/workbench")
        self.assertEqual(status, 307)
        self.assertTrue(headers[b"location"].endswith(b"/workbench/"))

    async def test_does_not_replace_unknown_assets_with_index(self):
        status, _, _ = await get(self.app, "/workbench/assets/missing.js")
        self.assertEqual(status, 404)

    async def test_does_not_serve_files_outside_build(self):
        status, body, _ = await get(self.app, "/workbench/../private.txt")
        self.assertEqual(status, 404)
        self.assertNotIn(b"not public", body)

    async def test_static_mount_does_not_shadow_api_routes(self):
        status, body, _ = await get(self.app, "/v1/probe")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})

    async def test_missing_build_is_explicitly_unavailable_and_logged(self):
        app = self.make_app(self.directory / "missing")
        with self.assertLogs("support_copilot.workbench", level="INFO") as logs:
            status, body, _ = await get(app, "/workbench/")
        self.assertEqual(status, 503)
        self.assertIn("not built", json.loads(body)["detail"])
        self.assertIn("workbench_assets_unavailable", logs.output[0])

    async def test_missing_index_does_not_expose_partial_build(self):
        (self.build_directory / "index.html").unlink()
        app = self.make_app(self.build_directory)
        with self.assertLogs("support_copilot.workbench", level="INFO"):
            status, _, _ = await get(app, "/workbench/assets/app.js")
        self.assertEqual(status, 503)

    async def test_api_remains_available_without_frontend_build(self):
        app = self.make_app(self.directory / "missing")
        status, body, _ = await get(app, "/v1/probe")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})


if __name__ == "__main__":
    unittest.main()
