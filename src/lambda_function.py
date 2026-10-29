from __future__ import annotations

import base64
import logging
import os

from storage import DynamoStore
from web import handle, json_response


store = None


def get_store():
    global store
    if store is None:
        store = DynamoStore(os.environ["TABELA_CERTIFICADOS"])
    return store


def handler(event: dict, context) -> dict:
    http = event.get("requestContext", {}).get("http", {})
    raw = event.get("body") or ""
    body = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")
    try:
        response = handle(http.get("method", "GET"), event.get("rawPath", "/"), event.get("headers") or {}, body, get_store())
    except Exception:
        logging.exception("Falha na requisição")
        response = json_response(500, {"erro": "Falha interna."})
    headers = {
        "Content-Type": response.content_type,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        **response.headers,
    }
    textual = response.content_type.startswith(("text/", "application/json"))
    return {
        "statusCode": response.status,
        "headers": headers,
        "body": response.body.decode("utf-8") if textual else base64.b64encode(response.body).decode("ascii"),
        "isBase64Encoded": not textual,
    }
