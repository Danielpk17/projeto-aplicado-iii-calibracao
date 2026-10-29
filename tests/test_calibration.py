import base64
from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import calibration
import lambda_function
import server
from storage import DynamoStore


def replace_sheet(old: str, new: str) -> bytes:
    source = BytesIO(calibration.sample_xlsx())
    output = BytesIO()
    with ZipFile(source) as reader, ZipFile(output, "w") as writer:
        for member in reader.infolist():
            content = reader.read(member.filename)
            if member.filename == "xl/worksheets/sheet1.xml":
                content = content.decode("utf-8").replace(old, new).encode("utf-8")
            writer.writestr(member, content)
    return output.getvalue()


class CalculationTests(unittest.TestCase):
    def test_model_template_is_approved_and_calculates_negative_error(self):
        result = calibration.calculate(calibration.parse_xlsx(calibration.sample_xlsx()))
        self.assertEqual(result["parecer_final"], "APROVADO")
        self.assertEqual(result["quantidade_pontos"], 3)
        self.assertEqual(Decimal(result["pontos"][1]["erro_sistematico"]), Decimal("-0.03333333333333333333333333"))

    def test_one_nonconforming_point_rejects_whole_certificate(self):
        data = replace_sheet('<c r="D4"><v>99.8</v></c>', '<c r="D4"><v>103.0</v></c>')
        result = calibration.calculate(calibration.parse_xlsx(data))
        self.assertEqual(result["parecer_final"], "REPROVADO")
        self.assertEqual(result["pontos"][2]["classificacao"], "FORA_DA_TOLERANCIA")

    def test_absolute_error_equal_to_lea_is_inside(self):
        points = [{"ponto": "P1", "padrao": Decimal("10"), "lea": Decimal("0.5"), "leituras": [Decimal("10.5")], "unidade": "bar"}]
        result = calibration.calculate(points)
        self.assertEqual(result["pontos"][0]["classificacao"], "DENTRO_DA_TOLERANCIA")

    def test_repeating_average_does_not_round_into_tolerance(self):
        points = [{
            "ponto": "P1", "padrao": Decimal("0"),
            "lea": Decimal("0.3333333333333333333333333333"),
            "leituras": [Decimal("0"), Decimal("0"), Decimal("1")], "unidade": "bar",
        }]
        result = calibration.calculate(points)
        self.assertEqual(result["pontos"][0]["classificacao"], "FORA_DA_TOLERANCIA")

    def test_negative_lea_is_rejected(self):
        data = replace_sheet('<c r="C2"><v>0.5</v></c>', '<c r="C2"><v>-0.5</v></c>')
        with self.assertRaisesRegex(calibration.SpreadsheetError, "LEA não pode ser negativo"):
            calibration.parse_xlsx(data)

    def test_formula_is_rejected(self):
        data = replace_sheet('<c r="D2"><v>0.1</v></c>', '<c r="D2"><f>1/10</f><v>0.1</v></c>')
        with self.assertRaisesRegex(calibration.SpreadsheetError, "fórmulas não são aceitas"):
            calibration.parse_xlsx(data)

    def test_invalid_file_is_rejected(self):
        with self.assertRaisesRegex(calibration.SpreadsheetError, "inválido"):
            calibration.parse_xlsx(b"not a zip")


class HttpFlowTests(unittest.TestCase):
    def test_upload_persists_and_can_be_retrieved(self):
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.DATABASE
            server.DATABASE = Path(temporary) / "calibracoes.sqlite3"
            httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                req = Request(
                    base + "/api/processar", data=calibration.sample_xlsx(), method="POST",
                    headers={"X-Filename": "modelo.xlsx", "X-Instrumento": "Manometro MD-01", "X-Responsavel": "Equipe"},
                )
                with urlopen(req) as response:
                    self.assertEqual(response.status, 201)
                    created = json.load(response)
                with urlopen(base + "/api/certificados/" + created["id"]) as response:
                    stored = json.load(response)
                with urlopen(base + "/api/certificados") as response:
                    history = json.load(response)
                self.assertEqual(stored["parecer_final"], "APROVADO")
                self.assertEqual(history[0]["id"], created["id"])
                self.assertEqual(stored["quantidade_pontos"], 3)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)
                server.DATABASE = original_database

    def test_bad_xlsx_returns_client_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            original_database = server.DATABASE
            server.DATABASE = Path(temporary) / "calibracoes.sqlite3"
            httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                req = Request(
                    f"http://127.0.0.1:{httpd.server_address[1]}/api/processar",
                    data=b"broken", method="POST", headers={"X-Filename": "broken.xlsx"},
                )
                with self.assertRaises(HTTPError) as context:
                    urlopen(req)
                self.assertEqual(context.exception.code, 400)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)
                server.DATABASE = original_database


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        if Item["id"] in self.items:
            raise RuntimeError("duplicado")
        self.items[Item["id"]] = dict(Item)

    def get_item(self, Key):
        item = self.items.get(Key["id"])
        return {"Item": item} if item else {}

    def query(self, IndexName, KeyConditionExpression, ExpressionAttributeValues, ScanIndexForward, Limit):
        rows = sorted((item for item in self.items.values() if item["tipo"] == ExpressionAttributeValues[":tipo"]), key=lambda item: item["criado_em"], reverse=not ScanIndexForward)
        return {"Items": rows[:Limit]}


def lambda_event(method, path, body=b"", headers=None):
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": headers or {},
        "body": base64.b64encode(body).decode("ascii") if body else None,
        "isBase64Encoded": bool(body),
    }


class LambdaTests(unittest.TestCase):
    def setUp(self):
        self.original_store = lambda_function.store
        lambda_function.store = DynamoStore("teste", table=FakeTable())

    def tearDown(self):
        lambda_function.store = self.original_store
        os.environ.pop("CHAVE_ACESSO", None)

    def upload(self, headers=None):
        base = {"x-filename": "modelo.xlsx", "x-instrumento": "Manometro MD-01"}
        return lambda_function.handler(lambda_event("POST", "/api/processar", calibration.sample_xlsx(), {**base, **(headers or {})}), None)

    def test_upload_through_function_url_persists_in_dynamodb(self):
        created = self.upload()
        self.assertEqual(created["statusCode"], 201)
        document = json.loads(created["body"])
        fetched = lambda_function.handler(lambda_event("GET", "/api/certificados/" + document["id"]), None)
        listed = lambda_function.handler(lambda_event("GET", "/api/certificados"), None)
        self.assertEqual(json.loads(fetched["body"])["parecer_final"], "APROVADO")
        self.assertEqual(json.loads(listed["body"])[0], {
            "id": document["id"], "criado_em": document["criado_em"], "instrumento": "Manometro MD-01",
            "arquivo": "modelo.xlsx", "parecer": "APROVADO", "quantidade_pontos": 3,
        })

    def test_qr_short_link_serves_mobile_page(self):
        response = lambda_function.handler(lambda_event("GET", "/c/1F6CC8E1FC30"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("consulta.js", response["body"])

    def test_template_download_is_base64_binary(self):
        response = lambda_function.handler(lambda_event("GET", "/modelo.xlsx"), None)
        self.assertTrue(response["isBase64Encoded"])
        self.assertEqual(base64.b64decode(response["body"]), calibration.sample_xlsx())

    def test_access_key_protects_upload_only(self):
        os.environ["CHAVE_ACESSO"] = "segredo"
        self.assertEqual(self.upload()["statusCode"], 401)
        self.assertEqual(self.upload({"x-chave": "errada"})["statusCode"], 401)
        self.assertEqual(self.upload({"x-chave": "segredo"})["statusCode"], 201)
        self.assertEqual(lambda_function.handler(lambda_event("GET", "/api/certificados"), None)["statusCode"], 200)

    def test_unknown_certificate_returns_404(self):
        response = lambda_function.handler(lambda_event("GET", "/api/certificados/000000000000"), None)
        self.assertEqual(response["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
