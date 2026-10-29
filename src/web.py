from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import json
import logging
import os
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from calibration import SpreadsheetError, calculate, parse_xlsx, sample_xlsx


PUBLIC = Path(__file__).resolve().parent / "public"
MAX_UPLOAD = 4_000_000
MAX_DOCUMENT = 350_000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/consulta": ("consulta.html", "text/html; charset=utf-8"),
    "/static/styles.css": ("static/styles.css", "text/css; charset=utf-8"),
    "/static/app.js": ("static/app.js", "text/javascript; charset=utf-8"),
    "/static/consulta.js": ("static/consulta.js", "text/javascript; charset=utf-8"),
    "/static/vendor/qrcode.min.js": ("static/vendor/qrcode.min.js", "text/javascript; charset=utf-8"),
    "/static/vendor/html5-qrcode.min.js": ("static/vendor/html5-qrcode.min.js", "text/javascript; charset=utf-8"),
}


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)


def json_response(status: int, data: dict | list) -> Response:
    return Response(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


def valid_identifier(identifier: str) -> bool:
    return len(identifier) == 12 and all(ch in "0123456789ABCDEF" for ch in identifier)


def authorized(headers: dict[str, str]) -> bool:
    expected = os.environ.get("CHAVE_ACESSO", "")
    if not expected:
        return True
    return hmac.compare_digest(unquote(headers.get("x-chave", "")).encode("utf-8"), expected.encode("utf-8"))


def handle(method: str, path: str, headers: dict[str, str], body: bytes, store) -> Response:
    headers = {key.lower(): value for key, value in headers.items()}
    if method == "GET":
        return handle_get(path, store)
    if method == "POST" and path == "/api/processar":
        return process(headers, body, store)
    return json_response(404, {"erro": "Rota não encontrada."})


def handle_get(path: str, store) -> Response:
    if path in STATIC:
        name, kind = STATIC[path]
        return Response(200, (PUBLIC / name).read_bytes(), kind)
    if path.startswith("/c/"):
        name, kind = STATIC["/consulta"]
        return Response(200, (PUBLIC / name).read_bytes(), kind)
    if path == "/modelo.xlsx":
        return Response(200, sample_xlsx(), XLSX, {"Content-Disposition": 'attachment; filename="modelo_calibracao.xlsx"'})
    if path == "/api/saude":
        return json_response(200, {"status": "ok", "armazenamento": type(store).__name__,
                                   "requer_chave": bool(os.environ.get("CHAVE_ACESSO"))})
    if path == "/api/certificados":
        return json_response(200, store.list())
    if path.startswith("/api/certificados/"):
        identifier = path.rsplit("/", 1)[-1].upper()
        document = store.get(identifier) if valid_identifier(identifier) else None
        return json_response(200, document) if document else json_response(404, {"erro": "Certificado não encontrado."})
    return json_response(404, {"erro": "Rota não encontrada."})


def process(headers: dict[str, str], body: bytes, store) -> Response:
    if not authorized(headers):
        return json_response(401, {"erro": "Chave de acesso inválida."})
    if not body or len(body) > MAX_UPLOAD:
        return json_response(413, {"erro": "Envie um arquivo XLSX de até 4 MB."})
    filename = unquote(headers.get("x-filename", "planilha.xlsx"))[:200]
    if not filename.lower().endswith(".xlsx"):
        return json_response(400, {"erro": "O arquivo precisa ter extensão .xlsx."})
    instrument = unquote(headers.get("x-instrumento", "")).strip()[:120]
    technician = unquote(headers.get("x-responsavel", "")).strip()[:120] or "Não informado"
    if not instrument:
        return json_response(400, {"erro": "Informe o instrumento."})
    try:
        result = calculate(parse_xlsx(body))
        document = {
            "id": uuid4().hex[:12].upper(),
            "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "instrumento": instrument,
            "responsavel": technician,
            "arquivo": filename,
            **result,
        }
        if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT:
            return json_response(413, {"erro": "O resultado excede o tamanho suportado. Divida a planilha em menos pontos."})
        store.save(document)
        return json_response(201, document)
    except SpreadsheetError as exc:
        return json_response(400, {"erro": str(exc)})
    except Exception:
        logging.exception("Falha inesperada no processamento")
        return json_response(500, {"erro": "Falha interna ao processar a planilha."})
