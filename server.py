from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from storage import SqliteStore
from web import MAX_UPLOAD, handle, json_response


DATABASE = BASE / "data" / "calibracoes.sqlite3"


class Handler(BaseHTTPRequestHandler):
    server_version = "CalibracaoMVP/2.0"

    def _send(self, response) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response.body)

    def do_GET(self) -> None:
        self._send(handle("GET", urlparse(self.path).path, dict(self.headers), b"", SqliteStore(DATABASE)))

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_UPLOAD:
            self._send(json_response(413, {"erro": "Envie um arquivo XLSX de até 4 MB."}))
            return
        body = self.rfile.read(length) if length > 0 else b""
        self._send(handle("POST", urlparse(self.path).path, dict(self.headers), body, SqliteStore(DATABASE)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibra: plataforma de certificados de calibração")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Aplicação disponível em http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
