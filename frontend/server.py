"""Frontend server for the Harmonizer SPA.

Serves the static SPA from the static/ directory and proxies
all /api/* and /health requests to the backend (BACKEND_URL).

Routes:
  GET /static/*        — static assets (CSS, JS, images)
  GET|POST|PUT|DELETE /api/* — proxied to backend
  GET /health          — proxied to backend
  GET /*               — serve index.html (SPA catch-all)
"""

import mimetypes
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
PORT = int(os.environ.get("FRONTEND_PORT", "3001"))

STATIC_DIR = Path(__file__).parent / "static"

# Ensure correct MIME types — Python's mimetypes module may return wrong
# values on some platforms (e.g. text/plain for .js on Alpine/Debian-slim).
MIME_OVERRIDES = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


class SPAHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = unquote(self.path.split("?")[0])
        if path.startswith("/static/"):
            # Strip leading "/static/" — STATIC_DIR already points to the static/ folder
            self._serve_static(path[len("/static/"):])
        elif path.startswith("/api/") or path == "/health":
            self._proxy("GET")
        else:
            self._serve_static("index.html")

    def do_POST(self) -> None:
        path = unquote(self.path.split("?")[0])
        if path.startswith("/api/"):
            self._proxy("POST")
        else:
            self._send(405, "text/plain", "Method Not Allowed")

    def do_PUT(self) -> None:
        path = unquote(self.path.split("?")[0])
        if path.startswith("/api/"):
            self._proxy("PUT")
        else:
            self._send(405, "text/plain", "Method Not Allowed")

    def do_DELETE(self) -> None:
        path = unquote(self.path.split("?")[0])
        if path.startswith("/api/"):
            self._proxy("DELETE")
        else:
            self._send(405, "text/plain", "Method Not Allowed")

    # --- Static file serving ---

    def _serve_static(self, rel_path: str) -> None:
        file_path = (STATIC_DIR / rel_path).resolve()
        # Safety: ensure we stay inside STATIC_DIR
        try:
            file_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send(403, "text/plain", "Forbidden")
            return

        if not file_path.exists() or not file_path.is_file():
            # Only fall back to index.html for SPA navigation routes
            # (paths without a file extension). Never serve HTML for
            # actual asset requests (.js, .css, .png, etc.) — return 404.
            if "." in Path(rel_path).name:
                self._send(404, "text/plain", f"Not found: {rel_path}")
                return
            index = STATIC_DIR / "index.html"
            if index.exists():
                self._send_file(index)
            else:
                self._send(404, "text/plain", "Not found")
            return

        self._send_file(file_path)

    def _send_file(self, path: Path) -> None:
        suffix = path.suffix.lower()
        mime_type = MIME_OVERRIDES.get(suffix)
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(str(path))
            mime_type = mime_type or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- API proxy ---

    def _proxy(self, method: str) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        target = BACKEND_URL + self.path
        req = urllib.request.Request(target, data=body, method=method)
        if body:
            ct = self.headers.get("Content-Type", "application/json")
            req.add_header("Content-Type", ct)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "application/json")
                data = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            content_type = e.headers.get("Content-Type", "application/json")
            data = e.read()
        except Exception as e:
            self._send(502, "text/plain", f"Backend unavailable: {e}")
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send(self, code: int, content_type: str, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[frontend] {self.address_string()} {args[0]}")


if __name__ == "__main__":
    print(f"Harmonizer frontend on :{PORT}")
    print(f"Static dir: {STATIC_DIR}")
    print(f"Backend: {BACKEND_URL}")
    server = HTTPServer(("0.0.0.0", PORT), SPAHandler)
    server.serve_forever()
