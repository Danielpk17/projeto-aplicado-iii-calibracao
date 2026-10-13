from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import sqlite3
from urllib.parse import unquote, urlparse
from uuid import uuid4

from calibration import SpreadsheetError, calculate, parse_xlsx, sample_xlsx


BASE = Path(__file__).resolve().parent
DATABASE = BASE / "data" / "calibracoes.sqlite3"
MAX_UPLOAD = 8_000_000
STATIC = {
    "/": (BASE / "index.html", "text/html; charset=utf-8"),
    "/static/styles.css": (BASE / "static" / "styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (BASE / "static" / "app.js", "text/javascript; charset=utf-8"),
}


def connect_db() -> sqlite3.Connection:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS certificados (
            id TEXT PRIMARY KEY,
            criado_em TEXT NOT NULL,
            instrumento TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            arquivo TEXT NOT NULL,
            parecer TEXT NOT NULL,
            quantidade_pontos INTEGER NOT NULL,
            resultado_json TEXT NOT NULL
        )
    """)
    connection.commit()
    return connection


def save_result(result: dict, instrument: str, technician: str, filename: str) -> dict:
    document = {
        "id": uuid4().hex[:12].upper(),
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instrumento": instrument,
        "responsavel": technician,
        "arquivo": filename,
        **result,
    }
    with closing(connect_db()) as connection:
        with connection:
            connection.execute(
                "INSERT INTO certificados VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (document["id"], document["criado_em"], instrument, technician, filename,
                 result["parecer_final"], result["quantidade_pontos"], json.dumps(document, ensure_ascii=False)),
            )
    return document


def list_results() -> list[dict]:
    with closing(connect_db()) as connection:
        rows = connection.execute(
            "SELECT id, criado_em, instrumento, arquivo, parecer, quantidade_pontos "
            "FROM certificados ORDER BY criado_em DESC, id DESC LIMIT 50"
        ).fetchall()
        return [dict(row) for row in rows]


def get_result(identifier: str) -> dict | None:
    with closing(connect_db()) as connection:
        row = connection.execute("SELECT resultado_json FROM certificados WHERE id = ?", (identifier,)).fetchone()
        return json.loads(row[0]) if row else None


class Handler(BaseHTTPRequestHandler):
    server_version = "CalibracaoMVP/1.0"

    def _respond(self, status: int, content: bytes, kind: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, data: dict | list) -> None:
        self._respond(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route in STATIC:
            path, kind = STATIC[route]
            self._respond(200, path.read_bytes(), kind)
        elif route == "/modelo.xlsx":
            self._respond(200, sample_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "modelo_calibracao.xlsx")
        elif route == "/api/certificados":
            self._json(200, list_results())
        elif route.startswith("/api/certificados/"):
            identifier = route.rsplit("/", 1)[-1]
            document = get_result(identifier) if identifier.isalnum() and len(identifier) == 12 else None
            self._json(200, document) if document else self._json(404, {"erro": "Certificado não encontrado."})
        else:
            self._json(404, {"erro": "Rota não encontrada."})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/processar":
            self._json(404, {"erro": "Rota não encontrada."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_UPLOAD:
            self._json(413, {"erro": "Envie um arquivo XLSX de até 8 MB."})
            return
        filename = unquote(self.headers.get("X-Filename", "planilha.xlsx"))[:200]
        if not filename.lower().endswith(".xlsx"):
            self._json(400, {"erro": "O arquivo precisa ter extensão .xlsx."})
            return
        instrument = unquote(self.headers.get("X-Instrumento", "Instrumento não informado")).strip()[:120]
        technician = unquote(self.headers.get("X-Responsavel", "Não informado")).strip()[:120]
        if not instrument:
            self._json(400, {"erro": "Informe o instrumento."})
            return
        try:
            points = parse_xlsx(self.rfile.read(length))
            document = save_result(calculate(points), instrument, technician, filename)
            self._json(HTTPStatus.CREATED, document)
        except SpreadsheetError as exc:
            self._json(400, {"erro": str(exc)})
        except Exception:
            logging.exception("Falha inesperada no processamento")
            self._json(500, {"erro": "Falha interna ao processar a planilha."})


def main() -> None:
    parser = argparse.ArgumentParser(description="MVP de certificados de calibração")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with closing(connect_db()):
        pass
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Aplicação disponível em http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
