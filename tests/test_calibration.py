from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

import calibration
import server


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


if __name__ == "__main__":
    unittest.main()
