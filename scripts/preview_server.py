"""
Local static preview server for the built frontend.

It serves frontend/dist on port 5173 and proxies /api requests to the
FastAPI backend on 127.0.0.1:8000. This avoids macOS LaunchAgent quirks
around long-running Node/Vite processes while still making the local app
viewable in a browser.
"""
from __future__ import annotations

import http.client
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "frontend" / "dist"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 5173
BACKEND_PROXY_TIMEOUT_SECONDS = 180


class PreviewHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy_api(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))

        conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=BACKEND_PROXY_TIMEOUT_SECONDS)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
        except Exception as exc:
            message = f"backend proxy error: {exc}".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return
        finally:
            conn.close()

        self.send_response(resp.status)
        for key, value in resp.getheaders():
            if key.lower() in {"transfer-encoding", "connection", "content-length"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path) -> None:
        payload = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_static(self) -> None:
        raw_path = urlsplit(self.path).path
        relative = raw_path.lstrip("/") or "index.html"
        candidate = (DIST_DIR / relative).resolve()
        dist_root = DIST_DIR.resolve()

        if not str(candidate).startswith(str(dist_root)) or not candidate.exists() or candidate.is_dir():
            candidate = dist_root / "index.html"

        if not candidate.exists():
            message = b"frontend/dist is missing; run npm run build in frontend first."
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return

        self._send_file(candidate)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            self._serve_static()

    def do_POST(self) -> None:
        self._proxy_api() if self.path.startswith("/api/") else self.send_error(405)

    def do_PUT(self) -> None:
        self._proxy_api() if self.path.startswith("/api/") else self.send_error(405)

    def do_DELETE(self) -> None:
        self._proxy_api() if self.path.startswith("/api/") else self.send_error(405)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[preview] {self.client_address[0]} {fmt % args}", flush=True)


def main() -> None:
    server = ThreadingHTTPServer((FRONTEND_HOST, FRONTEND_PORT), PreviewHandler)
    print(f"Preview server listening on http://{FRONTEND_HOST}:{FRONTEND_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
