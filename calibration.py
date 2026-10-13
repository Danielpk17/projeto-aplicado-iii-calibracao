from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePosixPath
import re
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_RE = re.compile(r"([A-Z]+)([0-9]+)$")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?)$")
MAX_POINTS = 1000
MAX_READINGS = 20


class SpreadsheetError(ValueError):
    pass


def _tag(name: str) -> str:
    return f"{{{MAIN}}}{name}"


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _decimal(value: str, label: str, row: int) -> Decimal:
    raw = str(value).strip().replace(" ", "")
    if not NUMBER_RE.fullmatch(raw):
        raise SpreadsheetError(f"Linha {row}: {label} deve ser um número válido.")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise SpreadsheetError(f"Linha {row}: {label} deve ser um número válido.") from exc
    if not result.is_finite():
        raise SpreadsheetError(f"Linha {row}: {label} deve ser finito.")
    return result


def _display(value: Decimal) -> str:
    return format(value, "f")


def _column_index(cell_reference: str) -> int:
    match = CELL_RE.fullmatch(cell_reference)
    if not match:
        raise SpreadsheetError("Referência de célula inválida no XLSX.")
    index = 0
    for ch in match.group(1):
        index = index * 26 + ord(ch) - ord("A") + 1
    return index - 1


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in item.iter(_tag("t"))) for item in root.iter(_tag("si"))]


def _first_sheet_path(archive: ZipFile) -> str:
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        first_sheet = next(workbook.iter(_tag("sheet")))
        relation_id = first_sheet.attrib[f"{{{REL}}}id"]
        target = next(r.attrib["Target"] for r in relationships.iter(f"{{{PKG_REL}}}Relationship") if r.attrib.get("Id") == relation_id)
    except (KeyError, StopIteration, ET.ParseError) as exc:
        raise SpreadsheetError("Não foi possível localizar a primeira aba do XLSX.") from exc
    path = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
    path = str(PurePosixPath(path))
    if ".." in PurePosixPath(path).parts or not path.startswith("xl/"):
        raise SpreadsheetError("Caminho de aba inválido no XLSX.")
    return path


def _read_rows(data: bytes) -> list[tuple[int, dict[int, str]]]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 200 or sum(item.file_size for item in infos) > 20_000_000:
                raise SpreadsheetError("Planilha grande demais para este MVP.")
            shared = _shared_strings(archive)
            root = ET.fromstring(archive.read(_first_sheet_path(archive)))
            result = []
            for row in root.iter(_tag("row")):
                row_number = int(row.attrib.get("r", len(result) + 1))
                cells: dict[int, str] = {}
                for cell in row.findall(_tag("c")):
                    if cell.find(_tag("f")) is not None:
                        raise SpreadsheetError(f"Linha {row_number}: fórmulas não são aceitas; informe valores medidos.")
                    index = _column_index(cell.attrib.get("r", ""))
                    if index > 100:
                        raise SpreadsheetError("A planilha contém colunas além do limite suportado.")
                    kind = cell.attrib.get("t")
                    if kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(_tag("t")))
                    else:
                        element = cell.find(_tag("v"))
                        value = element.text if element is not None and element.text is not None else ""
                        if kind == "s" and value:
                            value = shared[int(value)]
                    cells[index] = value.strip()
                if any(cells.values()):
                    result.append((row_number, cells))
                if len(result) > MAX_POINTS + 1:
                    raise SpreadsheetError(f"A planilha excede {MAX_POINTS} pontos de ensaio.")
            return result
    except SpreadsheetError:
        raise
    except (BadZipFile, KeyError, IndexError, ValueError, ET.ParseError) as exc:
        raise SpreadsheetError("Arquivo XLSX inválido ou corrompido.") from exc


def parse_xlsx(data: bytes) -> list[dict]:
    rows = _read_rows(data)
    if len(rows) < 2:
        raise SpreadsheetError("A planilha precisa de cabeçalho e ao menos um ponto de ensaio.")
    header = {}
    for col, value in rows[0][1].items():
        name = _normal(value)
        if name in header:
            raise SpreadsheetError(f"Cabeçalho duplicado: {value}.")
        if name:
            header[name] = col
    aliases = {
        "ponto": ("ponto", "ponto_de_ensaio"),
        "padrao": ("valor_padrao", "padrao", "valor_de_referencia", "referencia", "valor_referencia"),
        "lea": ("lea", "limite_de_erro_admissivel", "limite_erro_admissivel"),
    }
    columns: dict[str, int] = {}
    for key, options in aliases.items():
        found = next((header[name] for name in options if name in header), None)
        if found is None:
            raise SpreadsheetError(f"Cabeçalho obrigatório ausente: {key}.")
        columns[key] = found
    reading_columns = sorted((int(name.split("_")[-1]), col) for name, col in header.items() if re.fullmatch(r"leitura_\d+", name))
    if not reading_columns or len(reading_columns) > MAX_READINGS:
        raise SpreadsheetError("Use entre 1 e 20 colunas chamadas Leitura 1, Leitura 2, etc.")
    if len({number for number, _ in reading_columns}) != len(reading_columns):
        raise SpreadsheetError("Há colunas de leitura duplicadas.")
    unit_col = header.get("unidade")
    points = []
    seen = set()
    for row_number, values in rows[1:]:
        point = values.get(columns["ponto"], "").strip()
        if not point:
            raise SpreadsheetError(f"Linha {row_number}: informe o ponto de ensaio.")
        if point in seen:
            raise SpreadsheetError(f"Linha {row_number}: ponto de ensaio duplicado: {point}.")
        seen.add(point)
        standard = _decimal(values.get(columns["padrao"], ""), "Valor Padrão", row_number)
        lea = _decimal(values.get(columns["lea"], ""), "LEA", row_number)
        if lea < 0:
            raise SpreadsheetError(f"Linha {row_number}: LEA não pode ser negativo.")
        readings = [
            _decimal(values[col], f"Leitura {number}", row_number)
            for number, col in reading_columns if values.get(col, "") != ""
        ]
        if not readings:
            raise SpreadsheetError(f"Linha {row_number}: informe ao menos uma leitura.")
        points.append({
            "ponto": point,
            "padrao": standard,
            "lea": lea,
            "leituras": readings,
            "unidade": values.get(unit_col, "") if unit_col is not None else "",
        })
    return points


def calculate(points: list[dict]) -> dict:
    if not points:
        raise SpreadsheetError("Nenhum ponto de ensaio foi informado.")
    rows = []
    for point in points:
        total = sum(point["leituras"], Decimal(0))
        count = Decimal(len(point["leituras"]))
        average = total / count
        error = average - point["padrao"]
        status = "DENTRO_DA_TOLERANCIA" if abs(total - point["padrao"] * count) <= point["lea"] * count else "FORA_DA_TOLERANCIA"
        rows.append({
            "ponto": point["ponto"],
            "unidade": point["unidade"],
            "padrao": _display(point["padrao"]),
            "lea": _display(point["lea"]),
            "leituras": [_display(value) for value in point["leituras"]],
            "media": _display(average),
            "erro_sistematico": _display(error),
            "classificacao": status,
        })
    return {
        "parecer_final": "APROVADO" if all(row["classificacao"] == "DENTRO_DA_TOLERANCIA" for row in rows) else "REPROVADO",
        "quantidade_pontos": len(rows),
        "pontos": rows,
    }


def sample_xlsx() -> bytes:
    rows = [
        ["Ponto", "Valor Padrão", "LEA", "Leitura 1", "Leitura 2", "Leitura 3", "Unidade"],
        ["P1", 0, "0.5", "0.1", "0.2", "0.0", "bar"],
        ["P2", 50, "0.5", "49.8", "50.0", "50.1", "bar"],
        ["P3", 100, "0.5", "99.8", "100.2", "100.0", "bar"],
    ]
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    sheet_rows = []
    for number, values in enumerate(rows, 1):
        cells = []
        for index, value in enumerate(values):
            ref = f"{letters[index]}{number}"
            if isinstance(value, (int, float)) or (number > 1 and index in (1, 2, 3, 4, 5)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                escaped = (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets><sheet name="Ensaios" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG_REL}"><Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    return output.getvalue()
