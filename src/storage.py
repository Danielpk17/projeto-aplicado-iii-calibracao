from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3


LIST_LIMIT = 50
SUMMARY_FIELDS = ("id", "criado_em", "instrumento", "arquivo", "parecer", "quantidade_pontos")


class SqliteStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
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

    def save(self, document: dict) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO certificados VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (document["id"], document["criado_em"], document["instrumento"], document["responsavel"],
                     document["arquivo"], document["parecer_final"], document["quantidade_pontos"],
                     json.dumps(document, ensure_ascii=False)),
                )

    def list(self) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT {', '.join(SUMMARY_FIELDS)} FROM certificados "
                "ORDER BY criado_em DESC, id DESC LIMIT ?", (LIST_LIMIT,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get(self, identifier: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT resultado_json FROM certificados WHERE id = ?", (identifier,)).fetchone()
            return json.loads(row[0]) if row else None


class DynamoStore:
    INDEX = "por_data"
    KIND = "CERT"

    def __init__(self, table_name: str, table=None) -> None:
        if table is None:
            import boto3
            table = boto3.resource("dynamodb").Table(table_name)
        self.table = table

    def save(self, document: dict) -> None:
        self.table.put_item(
            Item={
                "id": document["id"],
                "tipo": self.KIND,
                "criado_em": document["criado_em"],
                "instrumento": document["instrumento"],
                "arquivo": document["arquivo"],
                "parecer": document["parecer_final"],
                "quantidade_pontos": document["quantidade_pontos"],
                "resultado_json": json.dumps(document, ensure_ascii=False),
            },
            ConditionExpression="attribute_not_exists(id)",
        )

    def list(self) -> list[dict]:
        response = self.table.query(
            IndexName=self.INDEX,
            KeyConditionExpression="tipo = :tipo",
            ExpressionAttributeValues={":tipo": self.KIND},
            ScanIndexForward=False,
            Limit=LIST_LIMIT,
        )
        return [
            {field: int(item[field]) if field == "quantidade_pontos" else item[field] for field in SUMMARY_FIELDS}
            for item in response.get("Items", [])
        ]

    def get(self, identifier: str) -> dict | None:
        item = self.table.get_item(Key={"id": identifier}).get("Item")
        return json.loads(item["resultado_json"]) if item else None

