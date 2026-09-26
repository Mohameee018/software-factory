from __future__ import annotations
from pathlib import Path
import mimetypes

TEXT_EXTENSIONS={".md",".txt",".json",".yaml",".yml",".csv",".xml",".html",".css",".js",".ts",".dart",".py",".java",".sql"}

def extract_text(path: str|Path):
    p=Path(path); ext=p.suffix.lower()
    try:
        if ext in TEXT_EXTENSIONS:
            return p.read_text(encoding="utf-8",errors="ignore")[:50000]
        if ext==".pdf":
            from pypdf import PdfReader
            return "\n\n".join((page.extract_text() or "") for page in PdfReader(str(p)).pages)[:50000]
        if ext==".docx":
            from docx import Document
            return "\n".join(x.text for x in Document(str(p)).paragraphs)[:50000]
    except Exception as exc:
        return f"[Could not extract text: {type(exc).__name__}: {exc}]"
    return ""

def describe(path: str|Path):
    p=Path(path)
    return {"name":p.name,"path":str(p),"extension":p.suffix.lower(),"mime":mimetypes.guess_type(p.name)[0] or "application/octet-stream"}
