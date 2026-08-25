#!/usr/bin/env python3
"""Estrae i valori base di un file XLSX usando solo la libreria standard."""
import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def column_index(reference):
    letters = re.match(r"[A-Z]+", reference or "A").group(0)
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - 64
    return value - 1


def main(filename):
    warnings = []
    with zipfile.ZipFile(filename) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", NS):
                shared.append("".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")))

        sheets = sorted(name for name in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name))
        all_rows = []
        for sheet_name in sheets:
            root = ET.fromstring(archive.read(sheet_name))
            matrix = []
            for row in root.findall(".//m:row", NS):
                values = []
                for cell in row.findall("m:c", NS):
                    index = column_index(cell.attrib.get("r"))
                    while len(values) <= index:
                        values.append("")
                    kind = cell.attrib.get("t")
                    value_node = cell.find("m:v", NS)
                    value = value_node.text if value_node is not None else ""
                    if kind == "s" and value:
                        value = shared[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t"))
                    values[index] = value
                if any(values):
                    matrix.append(values)
            if not matrix:
                continue
            headers = [str(value).strip() or f"colonna_{i + 1}" for i, value in enumerate(matrix[0])]
            for values in matrix[1:]:
                all_rows.append({header: values[i] if i < len(values) else "" for i, header in enumerate(headers)})
        text = "\n".join(" | ".join(str(value) for value in row.values()) for row in all_rows)
        print(json.dumps({"rows": all_rows, "text": text, "warnings": warnings}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as exc:
        print(json.dumps({"rows": [], "text": "", "warnings": [str(exc)]}, ensure_ascii=False))
