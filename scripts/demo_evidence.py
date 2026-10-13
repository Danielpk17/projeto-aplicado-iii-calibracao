"""Gera planilhas de demonstração e registra dois fluxos reais no servidor local."""

from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration import sample_xlsx  # noqa: E402


BASE = Path(__file__).resolve().parents[1]
EXAMPLES = BASE / "exemplos"
EVIDENCE = BASE / "evidencias"


def rejected_workbook(data: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(data)) as reader, ZipFile(output, "w") as writer:
        for member in reader.infolist():
            payload = reader.read(member.filename)
            if member.filename == "xl/worksheets/sheet1.xml":
                payload = payload.replace(b'<c r="D4"><v>99.8</v></c>', b'<c r="D4"><v>103.0</v></c>')
            writer.writestr(member, payload)
    return output.getvalue()


def submit(base_url: str, filename: str, data: bytes) -> dict:
    request = Request(
        base_url + "/api/processar",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "X-Filename": quote(filename),
            "X-Instrumento": quote("Manômetro digital MD-01"),
            "X-Responsavel": quote("Equipe de demonstração"),
        },
    )
    with urlopen(request) as response:
        if response.status != 201:
            raise RuntimeError(f"HTTP inesperado: {response.status}")
        return json.load(response)


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    EXAMPLES.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    approved = sample_xlsx()
    rejected = rejected_workbook(approved)
    (EXAMPLES / "calibracao_aprovada.xlsx").write_bytes(approved)
    (EXAMPLES / "calibracao_reprovada.xlsx").write_bytes(rejected)
    for name, filename, data in [
        ("aprovado", "calibracao_aprovada.xlsx", approved),
        ("reprovado", "calibracao_reprovada.xlsx", rejected),
    ]:
        result = submit(base_url, filename, data)
        (EVIDENCE / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name.upper()}: HTTP 201 | certificado {result['id']} | {result['parecer_final']} | {result['quantidade_pontos']} pontos")


if __name__ == "__main__":
    main()
