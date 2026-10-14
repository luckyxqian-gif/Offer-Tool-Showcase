#!/usr/bin/env python3
"""Serve one resume HTML on an isolated localhost URL for temporary QA."""

from __future__ import annotations

import argparse
import functools
import secrets
import shutil
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class PreviewError(ValueError):
    """Raised when an HTML file cannot be previewed safely."""


class PreviewHandler(SimpleHTTPRequestHandler):
    """Serve only the generated token path without directory listings or caching."""

    allowed_path = ""

    def _allowed(self) -> bool:
        return urlsplit(self.path).path == self.allowed_path

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP method name
        if not self._allowed():
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - inherited HTTP method name
        if not self._allowed():
            self.send_error(404)
            return
        super().do_HEAD()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def preview(input_path: Path, port: int) -> None:
    input_path = input_path.expanduser().resolve()
    if not input_path.is_file():
        raise PreviewError(f"找不到成品 HTML：{input_path}")
    if input_path.suffix.lower() != ".html":
        raise PreviewError("预览输入必须使用 .html 扩展名")
    if not 0 <= port <= 65535:
        raise PreviewError("端口必须在 0–65535 之间；0 表示自动选择随机可用端口")

    with tempfile.TemporaryDirectory(prefix="resume-tailor-preview-") as directory:
        filename = f"{secrets.token_urlsafe(18)}.html"
        shutil.copyfile(input_path, Path(directory) / filename)
        PreviewHandler.allowed_path = f"/{filename}"
        handler = functools.partial(PreviewHandler, directory=directory)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        server.daemon_threads = True
        actual_port = server.server_address[1]
        print(f"http://127.0.0.1:{actual_port}/{filename}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="实际生成的成品 HTML")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="仅绑定 127.0.0.1；默认 0 自动选择随机可用端口",
    )
    args = parser.parse_args()
    try:
        preview(args.input, args.port)
    except PreviewError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
