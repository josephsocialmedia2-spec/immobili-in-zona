#!/usr/bin/env python3
"""Estrae testo DOCX usando solo zipfile e XML standard."""
import sys
import zipfile
from xml.etree import ElementTree as ET


def main(filename):
    with zipfile.ZipFile(filename) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter():
        if paragraph.tag.endswith("}p"):
            text = "".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
            if text:
                paragraphs.append(text)
    print("\n".join(paragraphs))


if __name__ == "__main__":
    main(sys.argv[1])
