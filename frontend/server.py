"""Minimal report viewer serving generated Markdown reports as HTML.

Provides:
- GET /           — list of all reports with links
- GET /view/{name} — render a single Markdown report as simple HTML
- GET /raw/{name}  — raw Markdown text

This is a lightweight placeholder for a future proper frontend.
No external dependencies required.
"""

import html
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/reports"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8001")
PORT = int(os.environ.get("FRONTEND_PORT", "3001"))


def _md_to_html(md: str) -> str:
    """Very basic Markdown to HTML conversion (no external deps)."""
    lines = md.split("\n")
    out: list[str] = []
    in_table = False
    in_code = False

    for line in lines:
        # Code blocks
        if line.startswith("```"):
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append("<pre>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        # Tables
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= {"-", " "} for c in cells):
                continue  # separator row
            if not in_table:
                out.append("<table border='1' cellpadding='4' cellspacing='0'>")
                in_table = True
            out.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
            continue
        elif in_table:
            out.append("</table>")
            in_table = False

        # Headers
        if line.startswith("####"):
            out.append(f"<h4>{html.escape(line[4:].strip())}</h4>")
        elif line.startswith("###"):
            out.append(f"<h3>{html.escape(line[3:].strip())}</h3>")
        elif line.startswith("##"):
            out.append(f"<h2>{html.escape(line[2:].strip())}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("- "):
            out.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            out.append(f"<p><strong>{html.escape(line[2:-2])}</strong></p>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip() == "":
            out.append("<br>")
        else:
            # Bold inline
            processed = html.escape(line)
            processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', processed)
            out.append(f"<p>{processed}</p>")

    if in_table:
        out.append("</table>")
    if in_code:
        out.append("</pre>")

    return "\n".join(out)


class ReportHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = unquote(self.path)

        if path == "/" or path == "":
            self._serve_index()
        elif path.startswith("/view/"):
            name = path[6:]
            self._serve_report_html(name)
        elif path.startswith("/raw/"):
            name = path[5:]
            self._serve_report_raw(name)
        else:
            self._send(404, "text/plain", "Not found")

    def _serve_index(self) -> None:
        reports = []
        for subdir in ["generated", "reviewed"]:
            d = REPORT_PATH / subdir
            if d.exists():
                for f in sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                    reports.append((subdir, f.name))

        body = "<html><head><title>Harmonizer Reports</title>"
        body += "<style>body{font-family:sans-serif;margin:40px;} a{color:#0366d6;}</style>"
        body += "</head><body>"
        body += "<h1>Harmonizer — Report Viewer</h1>"
        body += f"<p>Backend: <a href='{BACKEND_URL}/health'>{BACKEND_URL}</a></p>"
        if reports:
            body += "<table border='1' cellpadding='8' cellspacing='0'>"
            body += "<tr><th>Report</th><th>Category</th><th>Actions</th></tr>"
            for subdir, name in reports:
                body += f"<tr><td>{html.escape(name)}</td><td>{subdir}</td>"
                body += f"<td><a href='/view/{name}'>View</a> | <a href='/raw/{name}'>Raw</a></td></tr>"
            body += "</table>"
        else:
            body += "<p>No reports found. Run an analysis first via the API.</p>"
        body += "</body></html>"
        self._send(200, "text/html", body)

    def _serve_report_html(self, name: str) -> None:
        content = self._read_report(name)
        if content is None:
            self._send(404, "text/plain", f"Report not found: {name}")
            return
        html_body = _md_to_html(content)
        page = f"""<html><head><title>{html.escape(name)}</title>
<style>body{{font-family:sans-serif;margin:40px;max-width:1200px;}}
table{{border-collapse:collapse;}} td,th{{padding:6px 10px;}}
pre{{background:#f6f8fa;padding:16px;overflow-x:auto;}}
h1{{color:#24292e;}} h2{{color:#0366d6;border-bottom:1px solid #e1e4e8;padding-bottom:8px;}}
</style></head><body>
<p><a href="/">&larr; Back to report list</a></p>
{html_body}
</body></html>"""
        self._send(200, "text/html", page)

    def _serve_report_raw(self, name: str) -> None:
        content = self._read_report(name)
        if content is None:
            self._send(404, "text/plain", f"Report not found: {name}")
            return
        self._send(200, "text/plain; charset=utf-8", content)

    def _read_report(self, name: str) -> str | None:
        for subdir in ["generated", "reviewed"]:
            f = REPORT_PATH / subdir / name
            if f.exists():
                return f.read_text(encoding="utf-8")
        return None

    def _send(self, code: int, content_type: str, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        encoded = body.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args) -> None:
        print(f"[frontend] {args[0]}")


if __name__ == "__main__":
    print(f"Starting report viewer on port {PORT}")
    print(f"Reports path: {REPORT_PATH}")
    server = HTTPServer(("0.0.0.0", PORT), ReportHandler)
    server.serve_forever()
